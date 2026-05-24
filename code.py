import time
import board
import busio
import displayio
import fourwire
from adafruit_display_text import label
import terminalio
import adafruit_ssd1680

# Integrated Bluetooth Libraries
from adafruit_ble import BLERadio
from adafruit_ble.advertising.standard import ProvideServicesAdvertisement
from adafruit_ble.services.nordic import UARTService

# Global tracking variable to hold the active hardware SPI register link
spi_bus = None

def create_fresh_display():
    """Forcefully tears down previous pins and initializes a raw display instance"""
    global spi_bus
    
    # 1. Forcefully release all high-level display frameworks from memory
    displayio.release_displays()
    time.sleep(0.1)

    # 2. SILICON DE-INIT FIX: Force close and un-use the hardware SPI pins
    if spi_bus is not None:
        try:
            spi_bus.deinit()
        except Exception:
            pass
        time.sleep(0.1)

    # 3. Open a completely clean SPI bus register mapping
    spi_bus = busio.SPI(clock=board.IO4, MOSI=board.IO6)

    # 4. Construct standard 4-line configuration bridge
    display_bus = fourwire.FourWire(
        spi_bus, command=board.IO5, chip_select=board.IO7, reset=board.IO3, baudrate=1000000
    )

    # 5. Return fresh initialized driver instance
    return adafruit_ssd1680.SSD1680(
        display_bus, 
        width=200, 
        height=200, 
        busy_pin=None, 
        rotation=180,  
        colstart=1,         
        rowstart=0, 
        highlight_color=0x000000
    )

# ==============================================================================
# 💡 THE AUTO-WRAP FIX: Slices long sentences cleanly to fit a 200px width
# ==============================================================================
def wrap_text_to_lines(string, max_chars=16):
    """Splits a single string into a list of chunks based on char limit per row"""
    words = string.split(" ")
    lines = []
    current_line = ""
    
    for word in words:
        # If a single word is insanely long, forcefully chop it
        if len(word) > max_chars:
            if current_line:
                lines.append(current_line)
                current_line = ""
            lines.append(word[:max_chars])
            current_line = word[max_chars:]
            continue
            
        if len(current_line) + len(word) + 1 <= max_chars:
            if current_line == "":
                current_line = word
            else:
                current_line += " " + word
        else:
            lines.append(current_line)
            current_line = word
            
    if current_line:
        lines.append(current_line)
        
    # Join the lines back together using native newline formatters
    return "\n".join(lines[:5]) # Hard cap at 5 vertical lines to prevent overflow
# ==============================================================================

def render_custom_text(message_text):
    """Rebuilds the screen profile and forces an instant pixel flash pass"""
    active_display = create_fresh_display()
    main_group = displayio.Group()

    # Draw White Background canvas
    bg_bitmap = displayio.Bitmap(200, 200, 1)
    bg_palette = displayio.Palette(1)
    bg_palette[0] = 0xFFFFFF  
    bg_sprite = displayio.TileGrid(bg_bitmap, pixel_shader=bg_palette)
    main_group.append(bg_sprite)

    # Draw Dark Top Header Banner Bar
    header_bitmap = displayio.Bitmap(200, 36, 1)
    header_palette = displayio.Palette(1)
    header_palette[0] = 0x000000  
    main_group.append(displayio.TileGrid(header_bitmap, pixel_shader=header_palette, x=0, y=0))

    # Typography Headers
    lbl_title = label.Label(terminalio.FONT, text="BLUETOOTH LINK", color=0xFFFFFF, x=55, y=18)
    
    # Run the wrapping algorithm on the text string right before drawing
    wrapped_message = wrap_text_to_lines(message_text, max_chars=16)
        
    # Initialized message layout block (Using line_spacing to gap wrapped rows cleanly)
    lbl_msg = label.Label(terminalio.FONT, text=wrapped_message, color=0x000000, scale=2, x=12, y=75, line_spacing=1.2)

    main_group.append(lbl_title)
    main_group.append(lbl_msg)
    
    active_display.root_group = main_group
    
    while True:
        try:
            active_display.refresh()
            break
        except RuntimeError:
            time.sleep(0.2)

# Global State Tracking Flags
text_to_render = "Connect App\nTo Send Text"
trigger_render_event = False 
last_refresh_time = 0
last_countdown_second = -1  
COOLDOWN_TIME = 16.0 

# Paint initial boot layout sequence
print("Executing Initial Boot Splash Canvas Draw...")
render_custom_text(text_to_render)
last_refresh_time = time.monotonic()

# 6. Spin up the Integrated ESP32-C3 BLE Stack
print("Initializing internal BLE wireless radio stack...")
ble = BLERadio()
ble.name = "Pico"  
uart_service = UARTService()
advertisement = ProvideServicesAdvertisement(uart_service)

print("Bluetooth beacon open. Advertising wireless lanes...")

# 7. Main Continuous Processing Loop
while True:
    try:
        ble.stop_advertising()
    except Exception:
        pass

    ble.start_advertising(advertisement)
    while not ble.connected:
        time.sleep(0.05)
    
    print("iPod Connected via Bluetooth!")
    ble.stop_advertising()
    last_countdown_second = -1  
    pending_queue_text = None
    
    while ble.connected:
        current_time = time.monotonic()
        time_elapsed = current_time - last_refresh_time
        
        # --- A. DECOUPLED BACKGROUND HARDWARE REFRESH PASS TRIGGER ---
        if trigger_render_event:
            trigger_render_event = False
            print(f"Executing update pass: '{text_to_render}'")
            render_custom_text(text_to_render)
            last_refresh_time = time.monotonic()
            uart_service.write("Screen Updated Successfully!\n")
        
        # --- B. CHECK FOR INCOMING BLE PACKETS ---
        if uart_service.in_waiting:
            raw_bytes = uart_service.readline()
            try:
                incoming_text = raw_bytes.decode("utf-8").strip()
                if incoming_text:
                    print(f"Received BLE input: '{incoming_text}'")
                    
                    if time_elapsed >= COOLDOWN_TIME:
                        pending_queue_text = None 
                        text_to_render = incoming_text
                        trigger_render_event = True
                        uart_service.write("Updating Screen...\n")
                    else:
                        pending_queue_text = incoming_text
                        time_remaining = int(COOLDOWN_TIME - time_elapsed)
                        if time_remaining <= 0:
                            time_remaining = 1
                        uart_service.write(f"Queued: '{incoming_text}'\n")
                        last_countdown_second = time_remaining 
            except Exception as e:
                print("Packet decoding trace exception:", e)

        # --- C. PROCESS DYNAMIC TICKING COUNTDOWN FEEDBACK ---
        if pending_queue_text is not None:
            time_remaining = int(COOLDOWN_TIME - time_elapsed)
            if time_remaining < 0:
                time_remaining = 0
                
            if time_remaining != last_countdown_second:
                last_countdown_second = time_remaining
                if time_remaining > 0:
                    uart_service.write(f"Refreshing in {time_remaining}s...\n")
                    print(f"Active Queue Countdown: {time_remaining}s remaining.")

            if time_elapsed >= COOLDOWN_TIME:
                print(f"Cooldown ended. Releasing queued text: '{pending_queue_text}'")
                text_to_render = pending_queue_text
                trigger_render_event = True 
                pending_queue_text = None 
                last_countdown_second = -1

        time.sleep(0.05) 
        
    print("Phone Disconnected. Re-opening advertising lanes...")

