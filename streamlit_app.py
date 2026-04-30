import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Import backend services
from database import SessionLocal
from services.stock_data import fetch_stock_data
from services.technical import calculate_technical_indicators, generate_technical_summary
from services.sentiment import analyze_sentiment
from services.fundamental import evaluate_fundamentals
from services.recommendation import generate_recommendation
from services.quant_backtest import run_institutional_backtest
from services.langchain_agent import StockAnalysisPipeline

# Page configuration
st.set_page_config(
    page_title="StockSense AI",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for premium dark aesthetics
st.markdown("""
<style>
    .reportview-container {
        background: #0B0E14;
        color: #F8F9FA;
    }
    .sidebar .sidebar-content {
        background: #151A23;
    }
    .stMetric {
        background: #1A202C;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    h1, h2, h3 {
        color: #60A5FA !important;
    }
</style>
""", unsafe_allow_html=True)

# Initialize pipeline caching to speed up loads
@st.cache_resource
def get_pipeline():
    return StockAnalysisPipeline()

pipeline = get_pipeline()

def get_db():
    return SessionLocal()

st.title("STOCKSENSE AI 📈")
st.markdown("### Institutional-Grade Quantitative Research Terminal")

# Sidebar
st.sidebar.header("Search & Configuration")
ticker = st.sidebar.text_input("Enter Ticker (e.g. AAPL, NVDA)", value="NVDA").upper()

# Preferences for AI
st.sidebar.subheader("AI Preferences")
risk_level = st.sidebar.selectbox("Risk Level", ["Low", "Medium", "High"], index=1)
investment_type = st.sidebar.selectbox("Investment Horizon", ["Short-term", "Long-term"], index=1)

analyze_btn = st.sidebar.button("Run Analysis", type="primary")

if analyze_btn and ticker:
    db = get_db()
    with st.spinner(f"Synthesizing Market Data for {ticker}..."):
        try:
            # 1. Fetch Data
            df = fetch_stock_data(ticker, period="1y", db=db)
            if df is None or df.empty:
                st.error("Data not found for this ticker. Please check the symbol and try again.")
            else:
                current_price = df.iloc[-1]['Close']
                price_change = current_price - df.iloc[-2]['Close']
                pct_change = (price_change / df.iloc[-2]['Close']) * 100
                
                # Header Metrics
                col1, col2, col3 = st.columns(3)
                col1.metric("Current Price", f"${current_price:.2f}", f"{price_change:.2f} ({pct_change:.2f}%)")
                
                # 2. Technicals
                tech_df = calculate_technical_indicators(df)
                tech_summary = generate_technical_summary(tech_df)
                col2.metric("RSI (14)", f"{tech_summary['rsi']:.2f}", tech_summary['rsi_interpretation'])
                col3.metric("Trend", tech_summary['trend_direction'])
                
                # 3. Chart
                st.subheader("Price Action (1Y)")
                fig = go.Figure(data=[go.Candlestick(x=df['Date'],
                                open=df['Open'],
                                high=df['High'],
                                low=df['Low'],
                                close=df['Close'])])
                fig.update_layout(template="plotly_dark", height=500, margin=dict(l=0, r=0, t=0, b=0))
                st.plotly_chart(fig, use_container_width=True)
                
                # 4. Deep Analysis via AI Pipeline
                st.subheader("AI Tactical Report")
                user_prefs = {
                    "risk_level": risk_level,
                    "investment_type": investment_type,
                    "focus_type": "Technical & Fundamental",
                    "budget_range": "Not specified",
                    "expected_return": "Not specified"
                }
                
                report = pipeline.run(ticker=ticker, user_prefs=user_prefs, db=db, user_question="")
                
                if "error" in report:
                    st.error(report["error"])
                else:
                    st.markdown(report['report_markdown'])
                    
                    st.subheader("AI Decision Matrix")
                    st.json({
                        "Action": report["decision"]["action"],
                        "Confidence": f"{report['decision']['confidence']}%",
                        "Risk Adjustment": report["decision"]["risk_adjustment"]
                    })
                    
        except Exception as e:
            st.error(f"An error occurred during analysis: {str(e)}")
