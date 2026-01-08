#!/bin/bash

cd  /home/ubuntu/final/OWS_Final/ 
source venv/bin/activate
python3 run_nifty.py &
python3 run_sensex.py &
deactivate
