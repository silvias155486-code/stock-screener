import os
import shutil
import certifi
import time
import requests

# --- 日本語パスによる通信エラーを回避する魔法のコード ---
safe_cert_path = os.path.join(os.getcwd(), "cacert.pem")
if not os.path.exists(safe_cert_path):
    try:
        shutil.copy2(certifi.where(), safe_cert_path)
    except Exception:
        pass
os.environ["CURL_CA_BUNDLE"] = safe_cert_path
os.environ["REQUESTS_CA_BUNDLE"] = safe_cert_path
# --------------------------------------------------------

import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go

st.set_page_config(page_title="米国株スクリーナー", layout="wide")
st.title("📈 米国株 割安・高配当スクリーナー (Pro版)")

st.sidebar.header("データ更新")
if st.sidebar.button("🔄 最新データを再取得 (リセット)"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.write("---")
st.sidebar.header("🔍 銘柄の直接検索")
search_query = st.sidebar.text_input("ティッカーまたは企業名を入力 (例: NVDA)")

st.sidebar.write("---")
st.sidebar.header("🌐 検索対象の市場")
market_choice = st.sidebar.radio(
    "対象を選んでください",
    [
        "S&P 500 (約500社 / 処理時間: 約4分)", 
        "米国全市場 NASDAQ・NYSE等 (約8000社 / 処理時間: 約1.5時間)"
    ]
)

st.sidebar.write("---")
st.sidebar.header("スクリーニング条件")

selected_sector = st.sidebar.selectbox(
    "セクターを選択", 
    ["すべて", "Technology", "Healthcare", "Financial Services", "Consumer Defensive", "Energy", "Industrials", "Communication Services", "Consumer Cyclical", "Utilities", "Real Estate", "Basic Materials"]
)

min_market_cap = st.sidebar.selectbox(
    "最低時価総額 (危険な小規模株の除外)",
    ["指定なし", "3億ドル以上 (小型株以上)", "20億ドル以上 (中型株以上)", "100億ドル以上 (大型株のみ)"]
)
max_pbr = st.sidebar.slider("PBRの上限 (倍)", 0.1, 10.0, 5.0, 0.1)
max_per = st.sidebar.slider("PERの上限 (倍)", 1.0, 100.0, 50.0, 1.0) 
min_roe = st.sidebar.slider("ROEの下限 (%)", -20.0, 50.0, 0.0, 1.0) 
min_dividend = st.sidebar.slider("配当利回りの下限 (%)", 0.0, 10.0, 0.0, 0.1)

st.sidebar.write("---")
st.sidebar.header("並び替え")
sort_option = st.sidebar.selectbox(
    "リストの表示順", 
    ["デフォルト", "配当利回りが高い順", "PBRが低い順", "PERが低い順", "ROEが高い順"] 
)

@st.cache_data(ttl=86400)
def get_sp500_tickers():
    try:
        url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        headers = {'User-Agent': 'Mozilla/5.0'}
        html = requests.get(url, headers=headers).text
        tables = pd.read_html(html)
        df = tables[0]
        tickers = df['Symbol'].tolist()
        return [t.replace('.', '-') for t in tickers]
    except Exception:
        return ["AAPL", "MSFT", "AMZN", "GOOGL", "META", "TSLA", "NVDA", "JNJ", "V", "PG", "JPM"]

@st.cache_data(ttl=86400)
def get_all_us_tickers():
    try:
        headers = {'User-Agent': 'PersonalStockScreener App (test@example.com)'}
        url = "https://www.sec.gov/files/company_tickers.json"
        response = requests.get(url, headers=headers)
        data = response.json()
        tickers = list(set([v['ticker'] for v in data.values()]))
        return [t.replace('.', '-') for t in tickers]
    except Exception as e:
        st.error(f"全米リストの取得に失敗しました: {e}")
        return get_sp500_tickers()

if "S&P 500" in market_choice:
    st.write("※現在は **S&P 500 の全銘柄（約500社）** を対象に検索しています。")
    tickers = get_sp500_tickers()
else:
    st.warning("⚠️ **米国全市場（約8,000社）** を対象に検索しています。初回のデータ取得には **約1時間〜1時間半** かかります。PCをスリープさせずにそのままお待ちください☕")
    tickers = get_all_us_tickers()

# ★★★ 最強の防弾シールド関数 ★★★
# どんな異常なデータ（文字、辞書、空っぽ等）が来ても、必ず数字（float）に変換してクラッシュを防ぐ
def safe_float(val):
    try:
        if val is None: return 0.0
        if isinstance(val, dict): return 0.0 
        return float(val)
    except Exception:
        return 0.0
# ★★★★★★★★★★★★★★★★★★★★★

@st.cache_data(ttl=3600, show_spinner="米国株のデータを全力で取得中です...（気長にお待ちください☕）")
def fetch_data(ticker_list):
    data = []
    for ticker in ticker_list:
        stock = yf.Ticker(ticker)
        try:
            info = stock.info 
            sector = info.get("sector", "Unknown")
            industry = info.get("industry", "Unknown") # 追加：同業他社を探すための「業種」
            
            # safe_floatを通すことで絶対にエラー落ちしなくなります
            pbr = safe_float(info.get("priceToBook"))
            per = safe_float(info.get("trailingPE"))
            roe = safe_float(info.get("returnOnEquity")) * 100 
            eps_growth = safe_float(info.get("earningsGrowth")) * 100 # 追加：EPS成長率
            market_cap = safe_float(info.get("marketCap"))
            
            div_rate = safe_float(info.get("dividendRate"))
            price = safe_float(info.get("currentPrice") or info.get("previousClose"))
            
            dividend_yield = 0.0
            if div_rate > 0 and price > 0:
                dividend_yield = (div_rate / price) * 100
            else:
                dy = safe_float(info.get("dividendYield"))
                if dy > 0:
                    dividend_yield = dy * 100 if dy < 0.2 else dy

            if dividend_yield > 20.0:
                dividend_yield = dividend_yield / 100
                
            target_price = safe_float(info.get("targetMeanPrice"))
            upside = 0.0
            if price > 0 and target_price > 0:
                upside = ((target_price / price) - 1) * 100
                
            revenue_growth = safe_float(info.get("revenueGrowth"))
            
            data.append({
                "Ticker": ticker,
                "Name": info.get("shortName", ticker),
                "Sector": sector,
                "Industry": industry, # 追加
                "Market Cap": market_cap, 
                "PBR": pbr,
                "PER": per, 
                "ROE (%)": roe, 
                "EPS Growth (%)": eps_growth, # 追加
                "Dividend Yield (%)": dividend_yield,
                "Current Price": price,
                "Target Price": target_price,
                "Upside (%)": upside,
                "Revenue Growth": revenue_growth
            })
        except Exception:
            pass
        
        time.sleep(0.5)
            
    return pd.DataFrame(data)

# データの取得
df = fetch_data(tickers)

if df.empty:
    st.error("⚠️ データの取得に失敗しました。時間をおいてから左側の「🔄 最新データを再取得」ボタンを押してください。")
else:
    cap_limit = 0
    if min_market_cap == "3億ドル以上 (小型株以上)": cap_limit = 300000000
    elif min_market_cap == "20億ドル以上 (中型株以上)": cap_limit = 2000000000
    elif min_market_cap == "100億ドル以上 (大型株のみ)": cap_limit = 10000000000
    
    filtered_df = df[
        (df["Market Cap"] >= cap_limit) &
        (df["PBR"] > 0) & (df["PBR"] <= max_pbr) & 
        (df["PER"] > 0) & (df["PER"] <= max_per) & 
        (df["ROE (%)"] >= min_roe) &
        (df["Dividend Yield (%)"] >= min_dividend)
    ]
    
    if selected_sector != "すべて":
        filtered_df = filtered_df[filtered_df["Sector"] == selected_sector]

    if search_query:
        filtered_df = filtered_df[
            filtered_df["Ticker"].str.contains(search_query, case=False, na=False) |
            filtered_df["Name"].str.contains(search_query, case=False, na=False)
        ]

    if sort_option == "配当利回りが高い順":
        filtered_df = filtered_df.sort_values(by="Dividend Yield (%)", ascending=False)
    elif sort_option == "PBRが低い順":
        filtered_df = filtered_df.sort_values(by="PBR", ascending=True)
    elif sort_option == "PERが低い順":
        filtered_df = filtered_df.sort_values(by="PER", ascending=True)
    elif sort_option == "ROEが高い順":
        filtered_df = filtered_df.sort_values(by="ROE (%)", ascending=False)

    st.sidebar.write("---")
    st.sidebar.header("データ出力")
    csv = filtered_df.to_csv(index=False).encode('utf-8-sig')
    st.sidebar.download_button(
        label="📥 表示中のリストをCSVで保存",
        data=csv,
        file_name='screener_results_v10.csv',
        mime='text/csv',
    )

    st.subheader(f"🔍 該当銘柄: {len(filtered_df)} 件 (データ取得成功: {len(df)}/{len(tickers)}社)")

    if len(filtered_df) > 0:
        for index, row in filtered_df.iterrows():
            ticker = row["Ticker"]
            with st.expander(f"【{ticker}】 {row['Name']} (PBR: {row['PBR']:.2f} / PER: {row['PER']:.2f} / ROE: {row['ROE (%)']:.1f}%)"):
                
                # --- 基本情報エリア ---
                col1, col2 = st.columns([1, 2])
                with col1:
                    st.write(f"**セクター:** {row['Sector']} ({row['Industry']})")
                    market_cap_b = row['Market Cap'] / 1000000000
                    st.write(f"**時価総額:** 約 ${market_cap_b:.1f}B")
                    st.write(f"**EPS成長率:** {row['EPS Growth (%)']:.1f} %")
                    st.write(f"**配当利回り:** {row['Dividend Yield (%)']:.2f} %")
                    
                    st.write("---") 
                    st.write(f"**現在の株価:** ${row['Current Price']:.2f}")
                    if row['Target Price'] > 0:
                        color = "#00FF00" if row['Upside (%)'] >= 0 else "#FF4B4B"
                        st.markdown(f"**平均目標株価:** ${row['Target Price']:.2f} (<span style='color:{color}; font-weight:bold;'>予想上値余地: {row['Upside (%)']:.1f}%</span>)", unsafe_allow_html=True)
                    else:
                        st.write("**平均目標株価:** データなし")
                    st.write("---")
                    
                    tv_url = f"https://jp.tradingview.com/chart/?symbol={ticker}"
                    st.markdown(f"[TradingViewでチャートを開く]({tv_url})", unsafe_allow_html=True)
                
                with col2:
                    stock = yf.Ticker(ticker)
                    financials = stock.financials
                    if not financials.empty:
                        try:
                            fin_df = financials.T
                            revenue = fin_df['Total Revenue'] / 1000000 if 'Total Revenue' in fin_df else None
                            net_income = fin_df['Net Income'] / 1000000 if 'Net Income' in fin_df else None
                            years = [str(date.year) for date in fin_df.index]
                            
                            years = years[::-1]
                            if revenue is not None: revenue = revenue[::-1]
                            if net_income is not None: net_income = net_income[::-1]
                            
                            fig = go.Figure()
                            if revenue is not None:
                                fig.add_trace(go.Bar(x=years, y=revenue, name='実績: 売上高', marker_color='#1f77b4'))
                            if net_income is not None:
                                fig.add_trace(go.Bar(x=years, y=net_income, name='実績: 純利益', marker_color='#ff7f0e'))
                            
                            rev_growth = row['Revenue Growth']
                            if revenue is not None and len(revenue) > 0 and rev_growth != 0:
                                latest_rev = revenue.iloc[-1]
                                proj_rev = latest_rev * (1 + rev_growth)
                                next_year = str(int(years[-1]) + 1) + " (予想)"
                                
                                fig.add_trace(go.Bar(
                                    x=[next_year], 
                                    y=[proj_rev], 
                                    name='予想: 売上高', 
                                    marker_color='#add8e6', 
                                    marker_pattern_shape="/" 
                                ))

                            fig.update_layout(title='業績推移と来期予想 (単位: 百万ドル)', barmode='group', height=300)
                            fig.update_xaxes(type='category')
                            
                            st.plotly_chart(fig, use_container_width=True)
                        except Exception as e:
                            st.write("グラフ化に失敗しました。")
                    else:
                        st.write("業績データなし")
                
                # --- ★追加：Bloomberg風 競合他社比較エリア ---
                st.write("---")
                st.markdown("#### 📊 競合他社（ピア）比較分析")
                
                # 同じ業種（Industry）の銘柄を探して時価総額順に並べる
                industry = row['Industry']
                if industry != "Unknown":
                    peers = df[(df['Industry'] == industry) & (df['Ticker'] != ticker)]
                    top_peers = peers.sort_values(by='Market Cap', ascending=False).head(4) # ライバル上位4社を抽出
                    
                    if not top_peers.empty:
                        # 自分とライバルを合体させる
                        comp_stocks = pd.concat([pd.DataFrame([row]), top_peers])
                        
                        # 表示用に綺麗に整形
                        comp_df = comp_stocks[['Ticker', 'Name', 'PER', 'ROE (%)', 'EPS Growth (%)', 'Market Cap']].copy()
                        comp_df['Market Cap'] = (comp_df['Market Cap'] / 1000000000).apply(lambda x: f"${x:.1f}B")
                        comp_df['PER'] = comp_df['PER'].apply(lambda x: f"{x:.1f} 倍")
                        comp_df['ROE (%)'] = comp_df['ROE (%)'].apply(lambda x: f"{x:.1f} %")
                        comp_df['EPS Growth (%)'] = comp_df['EPS Growth (%)'].apply(lambda x: f"{x:.1f} %")
                        
                        # テーブルとして美しく表示
                        st.dataframe(comp_df, hide_index=True, use_container_width=True)
                    else:
                        st.write("※比較可能な同じ業種のデータがありません。")
                else:
                    st.write("※業種データが取得できないため比較できません。")

    else:
        st.write("条件に一致する銘柄がありません。")

