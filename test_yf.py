import yfinance as yf
df = yf.Ticker("AAPL").history(period="1y")
df.reset_index(inplace=True)
print("Columns present:", df.columns.tolist())
try:
    df['Date'] = df['Date'].dt.strftime('%Y-%m-%d')
    records = df[['Date', 'Open', 'High', 'Low', 'Close', 'Volume']].dropna().to_dict(orient="records")
    print("Success. Extracted", len(records), "records.")
    print("First record:", records[0])
except Exception as e:
    print("Error:", str(e))
