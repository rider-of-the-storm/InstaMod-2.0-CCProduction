#!/usr/bin/env python
# Ugly hack from Rider

import psutil
import subprocess
import os
import time
from datetime import datetime

# Set some variables

ctstamp = (time.strftime("%m/%d/%y %H:%M:%S"))
ctimem = (time.strftime("%M"))
ctimeh = (time.strftime("%H"))
script_name = "Main.py"
pid = ""

# Define logging the scripts actions

def slog(string):
        if not os.path.exists('./status.log'):
            elog = open('./status.log', 'w')
            elog.write('Status log for Instamod2'  + ' that began on. ' + (str(ctstamp)) + '\n' + 'Items logged here refer to hourly restarts and script failure restarts' + '\n')
            elog.write(ctstamp + ' ' + string + '\n')
            elog.close()
        else:
            elog = open('./status.log', 'a')
            elog.write(ctstamp + ' ' + string + '\n')
            elog.close()

# Check if Instamod is running by PID and start if not also restarts Instamod if it is not runnning

ps_out = subprocess.Popen("ps -auxw".split(' '), stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.read().decode('UTF-8').split("\n") # Launch command line and gather output
for entry in ps_out:  # Loop over returned lines of ps
    if script_name in entry:
        pid = entry.split()[1] # retrieve second entry in line
        break

#print(pid)  # Uncomment to see if Pid is being caught

if (pid) is not "":
    run = 'True'
    if str(run) == 'True' and ctimem == "50":
        txt = (" Instamod being killed by pid " + pid)
        slog(str(txt))
        subprocess.call (["/bin/kill", pid])
        time.sleep(10)
        txt = (" Scheduled restart of Instamod")
        slog(str(txt))
        subprocess.call (["/usr/bin/python", "./Main.py"])
        exit
else:
    run = 'False'
    txt = (' Instamod not running! Starting Instamod')
    slog(str(txt))
    subprocess.call (["/usr/bin/python", "./Main.py"])
