###############################################################################
# Strategy:
# User provides a directory containing schedules to be run.
# A thread is spawned that periodically loads schedules in the directory,
# checks the day and time the schedule should be executed, and queues schedules
# ready to be executed.
# The queue consumer pops schedules and executes them.
###############################################################################
from datetime import datetime
from datetime import timedelta
import json
import os
import serial
import sys
import time
import signal
import threading
import queue

# Set to true to terminate the program.
end_program = False

# Initialize serial port to 9600 baud - that's what the arduino uses.
ser = serial.Serial(
    port=sys.argv[1],
    baudrate=9600
)


def serial_write(message):
    """
    Write a string to the serial port.
    :return:
    """
    ser.write(message.encode('utf-8'))


def shutdown_sprinklers():
    """
    Shuts down and exits.
    """
    print("Shutting off sprinklers and exiting")
    serial_write('0')
    ser.close()
    sys.exit()


def switch_to_station(station):
    """
    Changes sprinkler station.
    Disables all sprinklers for a short period to let the previous station
    finish, then starts the next station.
    """
    print("Start station change")
    serial_write('0')
    time.sleep(5)
    serial_write(station)
    print("End station change")


def schedule_loader():
    """
    Function to load schedules and queue those that are ready to be executed.

    Checks schedules every minute to see if they should be run.

    :return:
    """

    # How frequently we'll check to see if it's time to run.
    one_minute = timedelta(minutes=1)

    # How frequently we wake up to see if it's a new minute.
    # Short enough to not be a bother when shutting down.
    sleep_time = timedelta(seconds=5)

    # The next time we should execute
    next_run = datetime.now() + one_minute

    while not end_program:
        current_time = datetime.now()

        if current_time >= next_run:
            next_run = datetime.now() + one_minute

            for file in os.listdir(sys.argv[2]):
                if file.endswith(".json"):
                    file = sys.argv[2] + "/" + file

                    # Suck up the json and load its values.
                    schedule = json.loads(open(file).read())

                    # Convert the time in the schedule to a time today.
                    schedule_time = datetime.strptime(schedule["time"], '%I:%M%p')
                    start_time = datetime.combine(datetime.today(), schedule_time.time())

                    # Check if it's the right day.
                    days_since_epoch = (datetime.utcnow() - datetime(1970, 1, 1)).days
                    if (days_since_epoch % int(schedule['daymod'])) != 0:
                        # Skip this schedule
                        continue

                    # Execute if the current time falls within the minute the
                    # schedule should be run.
                    if current_time >= start_time and current_time < (start_time + one_minute):
                        # Queue the schedule for execution.
                        print(str(current_time) + ": Queueing schedule: " + schedule['name'])
                        schedule_queue.put(schedule)
                # Else it's not a schedule file
            # End for
        # Else we don't run
        time.sleep(sleep_time.seconds)


def signal_handler(signal, fame):
    """
    Handles signals, duh.
    """
    shutdown_sprinklers()

# Capture CTRL-C.
signal.signal(signal.SIGINT, signal_handler)

# Ensure the sprinklers are off.
switch_to_station('0')

# Queue containing schedules that need to be executed.
schedule_queue = queue.Queue()

# Launch schedule loader thread.
print(str(datetime.now()) + " : Beginning schedule scan")
loader_thread = threading.Thread(target=schedule_loader)
loader_thread.start()

while not end_program:
    try:
        schedule = schedule_queue.get(timeout=1)
    except queue.Empty:
        # The queue will be empty quite often.
        pass
    else:
        print(str(datetime.now()) + " : Executing schedule: " + schedule['name'])
        for entry in schedule['schedule']:
            station = entry['station']
            time_in_minutes = int(entry['runtime'])

            print(str(datetime.now()) + " : Starting station " + station + ", will run for " + str(time_in_minutes) + " minutes")
            switch_to_station(station)
            time.sleep(time_in_minutes * 60)

        # Turn off sprinklers, but don't exit program
        switch_to_station('0')
        print("Schedule complete.")

print("Joining threads...")
shutdown_sprinklers()
loader_thread.join()
print("Have a nice day")
