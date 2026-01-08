# kite_project01
 Algo Trading System Specification


1. Overview
Two Python scripts run independently on an AWS EC2 m2.medium instance — one for Nifty, one for Sensex. Both use anchored VWAP on the straddle premium chart (ATM CE + ATM PE) to decide whether to initiate an option buy (debit spread) or sell (Batman) strategy.


2. Strategy Logic

A. Option Buying (Debit Spread)
- Condition: If market closes above anchored VWAP and breaks opening range on 1-min candle. ????
- Action:
- Buy ATM CE
- Sell OTM CE (form debit spread)
- Stop Loss: Previous swing low of straddle premium range; trail upwards if new HH (Higher High) forms.

B. Option Selling (Batman Spread)
- Condition: straddle premium makes lower lows.
- Action:
- Sell CE & PE ~2.5% away
- Buy hedge legs ~1.25% away
- Stop Loss: Previous swing high; adjusted on breakout of straddle premium.


- Position Shift: Entire Batman moved as index crosses pivot levels.
- Pivot based on last X-minute range (configurable).
- Shift if index moves in N-point steps (50 Nifty / 100 Sensex; configurable).
- Gaps and hedges % configurable based on DTE.


3. Risk Management (RMS)
- Initial RMS Cap: Example -1,00,000 set each morning.
- Live MTM Tracking: Highest MTM deducted from RMS to prevent over-losses.
- Exit Triggers:
- RMS limit breach
- SL hit on range high/low
- Rolling profit reached (configurable)


4. Order Management

Order Execution
- Limit order with x% buffer (configurable)
- If not filled in y sec, convert to market
- Handle order slicing and exchange freeze limits

Emergency Exit Command
- Command: /exit_positions
- Effect: Exits all open positions created by the script via market orders
- Exclusion: Manual trades untouched (script uses internal log/db to verify)

5. Console Display (Real-Time Monitoring)
Console will continuously display:

[CONFIG]
Index: Nifty | Strategy: Batman | Expiry: 30-May-2025
VWAP Anchored: 9:20 AM | Pivot Range: 15 min | Increment: 50 pts
Straddle Gap: Sell ±2.5% | Hedge ±1.25% | Order Buffer: 0.3% | Fill Time: 5 sec

[RISK]
Max RMS: -1,00,000 | Highest MTM: -26,500 | Remaining RMS: -73,500

[TRADE]
Current MTM: -8,250 | Open Strategy: Batman | SL at: 22610 (range high)

6. Configurable Parameters
All the below will be modifiable via a .yaml or .json config file or Web UI in next phase:
- Pivot calculation window (default 15 mins)
- Shift threshold (e.g., 50 pts Nifty, 100 pts Sensex)
- CE/PE sell and hedge gap % (based on DTE)
- Order buffer % and time delay
- Expiry date
- RMS cap
- Trail logic toggle
- Console verbosity
- Stop-loss buffer percentage (default 1%)
- Anchored VWAP display in console


7. Collaboration & Testing

- You will be available for dev queries during the development cycle.

- Delivery deadline: June 15th.

- Live market test: June 16th & 17th with 1–2 lots.

- Post-delivery support


#Redis Keys #
strategy:heartbeat # Stores strategy heartbeat details
strategy:execution_status # Stores strategy status (running, stopped, etc.)