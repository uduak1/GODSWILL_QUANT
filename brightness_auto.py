import psutil
import screen_brightness_control as sbc
import time

def set_auto_brightness():
    # Get battery information
    battery = psutil.sensors_battery()
    
    if battery is None:
        print("No battery detected. This script is meant for laptops.")
        return

    percent = battery.percent
    plugged_in = battery.power_plugged

    # Define your brightness rules here
    if plugged_in:
        target_brightness = 100  # 100% brightness when charging
    else:
        if percent > 75:
            target_brightness = 80
        elif percent > 50:
            target_brightness = 60
        elif percent > 25:
            target_brightness = 40
        elif percent > 10:
            target_brightness = 20
        else:
            target_brightness = 10  # Save battery when critically low

    try:
        # Get current brightness to avoid setting it repeatedly (saves resources)
        current_brightness = sbc.get_brightness(display=0)[0]
        
        if current_brightness != target_brightness:
            sbc.set_brightness(target_brightness, display=0)
            print(f"Battery: {percent}% | Plugged In: {plugged_in} | Brightness changed from {current_brightness}% to {target_brightness}%")
        else:
            # Print status so you know it's working
            print(f"Battery: {percent}% | Plugged In: {plugged_in} | Brightness is optimal at {target_brightness}%")
            
    except Exception as e:
        print(f"Could not adjust brightness: {e}")

# Run the check every 60 seconds
if __name__ == "__main__":
    print("Starting Auto-Brightness Monitor... Press Ctrl+C to stop.")
    try:
        while True:
            set_auto_brightness()
            time.sleep(60) # Wait 60 seconds before checking again
    except KeyboardInterrupt:
        print("\nAuto-Brightness Monitor stopped.")