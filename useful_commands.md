## ADB Connection Commands

List all devices currently connected (via USB or Wi-Fi): `adb devices`

Restart ADB in TCP mode to prepare for a wireless connection: `adb tcpip 5555`

Connect to the headset wirelessly (replace with your headset's actual IP): `adb connect 192.168.0.100:5555`

Disconnect a specific wireless connection: `adb disconnect 192.168.0.100:5555`

Disconnect all wireless devices: `adb disconnect`

## ADB App Installation Commands

Install a new APK file to the headset: `adb install /path/to/your/app.apk`

Reinstall or update an existing app without losing its saved data (-r means replace): `adb install -r /path/to/your/app.apk`

Uninstall an app from the headset (requires the Android package name, not the APK file name): `adb uninstall com.YourCompany.YourApp`

## ADB Device Utility Commands

Find the headset's IP address (requires the headset to be connected via USB first): `adb shell ip route`

Reboot the headset remotely: `adb reboot`

Kill the ADB server entirely (useful if connections get glitched or frozen): `adb kill-server`

Start the ADB server (usually happens automatically when you run a command): `adb start-server`

## Keyboard Controls:
```
W/S: Forward/Backward
A/D: Left/Right
Space/Shift: Up/Down
Q/E: Rotate
```
