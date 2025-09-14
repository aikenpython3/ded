import pygame
from gpiozero import OutputDevice
import time
import os
import json
import sys
from datetime import datetime

# Define relay pins (BCM numbering)
RELAY_PINS = {
    'ac': 17,          # Кондиционер
    'heater_vent': 19, # Открылка для обогрева
    'room3': 22,       # Комната 3
    'room2': 23,       # Комната 2
    'room1': 24,       # Комната 1
    'supply': 25,      # Приток
    'room4': 26,       # Комната 4
    'room5': 27        # Комната 5
}

# Temperature sensor setup
base_dir = '/sys/bus/w1/devices/'
sensor_ids = {
    'room1': '28-0b2396934aee',
    'room2': '28-0b2396b717c8',
    'room3': '28-00000036fd20',
    'room4': '28-0b2396b8f8d6',
    'room5': '28-0b23965334fa'
}

# Default temperature settings
DEFAULT_SETTINGS = {
    'room1': {'min_temp': 20, 'max_temp': 25, 'manual_heat': False, 'manual_cool': False},
    'room2': {'min_temp': 20, 'max_temp': 25, 'manual_heat': False, 'manual_cool': False},
    'room3': {'min_temp': 20, 'max_temp': 25, 'manual_heat': False, 'manual_cool': False},
    'room4': {'min_temp': 20, 'max_temp': 25, 'manual_heat': False, 'manual_cool': False},
    'room5': {'min_temp': 20, 'max_temp': 25, 'manual_heat': False, 'manual_cool': False}
}

# Initialize GPIO with gpiozero
relay_devices = {}
gpio_initialized = False

try:
    # Initialize all relay devices
    for name, pin in RELAY_PINS.items():
        # Для реле, активируемых LOW уровнем: active_high=False
        # Для реле, активируемых HIGH уровнем: active_high=True
        relay_devices[name] = OutputDevice(pin, active_high=False, initial_value=False)
    
    gpio_initialized = True
    print("GPIO initialized successfully with gpiozero")
    
except Exception as e:
    print(f"Error initializing GPIO with gpiozero: {e}")
    print("Running in simulation mode without GPIO control")

# Load and save settings
def load_settings():
    try:
        with open('climate_settings.json', 'r') as f:
            return json.load(f)
    except:
        return DEFAULT_SETTINGS.copy()

def save_settings(settings):
    with open('climate_settings.json', 'w') as f:
        json.dump(settings, f, indent=4)

# Temperature reading functions
def read_temp_raw(device_file):
    try:
        with open(device_file, 'r') as f:
            return f.readlines()
    except:
        return None

def read_temp(sensor_id):
    device_file = base_dir + sensor_id + '/w1_slave'
    try:
        lines = read_temp_raw(device_file)
        if not lines:
            return None
            
        while lines[0].strip()[-3:] != 'YES':
            time.sleep(0.2)
            lines = read_temp_raw(device_file)
            if not lines:
                return None
                
        equals_pos = lines[1].find('t=')
        if equals_pos != -1:
            temp_string = lines[1][equals_pos+2:]
            return float(temp_string) / 1000.0
    except:
        return None
    return None

# Relay control
def set_relay(relay_name, state):
    """Set relay state (True=ON, False=OFF)"""
    if not gpio_initialized:
        print(f"GPIO not initialized - simulating {relay_name} set to {'ON' if state else 'OFF'}")
        return True
        
    try:
        relay = relay_devices[relay_name]
        if state:
            relay.on()
        else:
            relay.off()
        
        print(f"[RELAY] {relay_name} set to {'ON' if state else 'OFF'}")
        return True
    except Exception as e:
        print(f"Error controlling relay {relay_name}: {e}")
        return False

# Test all relays
def test_all_relays():
    """Test all relays by turning them on and off sequentially"""
    print("Testing all relays...")
    
    # Turn all relays off first
    for name in relay_devices:
        set_relay(name, False)
    time.sleep(1)
    
    # Test each relay one by one
    for name in relay_devices:
        print(f"Testing {name}...")
        set_relay(name, True)  # Turn on
        time.sleep(2)  # Keep on for 2 seconds
        set_relay(name, False)  # Turn off
        time.sleep(1)  # Pause between relays
    
    print("Relay test completed")

# Main application class
class ClimateControlApp:
    def __init__(self):
        pygame.init()
        self.width, self.height = 800, 480
        self.screen = pygame.display.set_mode((self.width, self.height))
        pygame.display.set_caption("Climate Control System")
        
        self.clock = pygame.time.Clock()
        self.font_large = pygame.font.SysFont(None, 36)
        self.font_medium = pygame.font.SysFont(None, 28)
        self.font_small = pygame.font.SysFont(None, 22)
        
        self.settings = load_settings()
        self.current_screen = "main"
        self.selected_room = None
        self.temperatures = {}
        self.room_states = {room: {'cooling': False, 'heating': False} for room in sensor_ids.keys()}
        
        # Colors
        self.colors = {
            'background': (240, 240, 240),
            'text': (0, 0, 0),
            'button': (200, 200, 200),
            'button_hover': (180, 180, 180),
            'active': (0, 200, 0),
            'inactive': (200, 0, 0),
            'hot': (255, 100, 100),
            'cold': (100, 100, 255),
            'normal': (100, 200, 100)
        }
        
        self.last_temp_update = 0
        self.last_control_update = 0
        
        # Test relays on startup
        test_all_relays()
        
    def get_room_status_text(self, room):
        """Get text description of room status"""
        if self.settings[room]['manual_heat']:
            return "Ручной обогрев"
        elif self.settings[room]['manual_cool']:
            return "Ручное охлаждение"
        elif self.room_states[room]['heating']:
            return "Авто обогрев"
        elif self.room_states[room]['cooling']:
            return "Авто охлаждение"
        else:
            temp = self.temperatures.get(room)
            if temp is None:
                return "Нет данных"
            elif temp > self.settings[room]['max_temp']:
                return "Слишком жарко"
            elif temp < self.settings[room]['min_temp']:
                return "Слишком холодно"
            else:
                return "Норма"
    
    def get_room_status_color(self, room):
        """Get color for room status"""
        if self.settings[room]['manual_heat'] or self.room_states[room]['heating']:
            return self.colors['hot']
        elif self.settings[room]['manual_cool'] or self.room_states[room]['cooling']:
            return self.colors['cold']
        else:
            temp = self.temperatures.get(room)
            if temp is None:
                return self.colors['text']
            elif temp > self.settings[room]['max_temp']:
                return self.colors['hot']
            elif temp < self.settings[room]['min_temp']:
                return self.colors['cold']
            else:
                return self.colors['normal']
        
    def draw_main_screen(self):
        self.screen.fill(self.colors['background'])
        
        # Title
        title = self.font_large.render("Climate Control System", True, self.colors['text'])
        self.screen.blit(title, (20, 20))
        
        # Time
        time_text = self.font_medium.render(datetime.now().strftime('%Y-%m-%d %H:%M:%S'), True, self.colors['text'])
        self.screen.blit(time_text, (self.width - time_text.get_width() - 20, 20))
        
        # Room temperatures and status
        y_pos = 80
        for room in sensor_ids.keys():
            temp = self.temperatures.get(room)
            
            # Determine color based on temperature
            if temp is not None:
                if temp > self.settings[room]['max_temp']:
                    color = self.colors['hot']
                    status = "TOO HOT"
                elif temp < self.settings[room]['min_temp']:
                    color = self.colors['cold']
                    status = "TOO COLD"
                else:
                    color = self.colors['normal']
                    status = "NORMAL"
                
                # Room temperature
                temp_text = self.font_medium.render(f"{room}: {temp:.1f}°C", True, color)
                self.screen.blit(temp_text, (50, y_pos))
                
                # Temperature status
                status_text = self.font_small.render(status, True, color)
                self.screen.blit(status_text, (250, y_pos))
                
                # System status indicators
                status_y = y_pos + 25
                if self.room_states[room]['cooling']:
                    cooling_text = self.font_small.render("❄️ Cooling", True, (0, 0, 255))
                    self.screen.blit(cooling_text, (250, status_y))
                elif self.room_states[room]['heating']:
                    heating_text = self.font_small.render("🔥 Heating", True, (255, 0, 0))
                    self.screen.blit(heating_text, (250, status_y))
                
                # Manual mode indicators
                if self.settings[room]['manual_heat']:
                    manual_text = self.font_small.render("🔧 Manual Heat", True, (255, 165, 0))
                    self.screen.blit(manual_text, (400, y_pos))
                elif self.settings[room]['manual_cool']:
                    manual_text = self.font_small.render("🔧 Manual Cool", True, (255, 165, 0))
                    self.screen.blit(manual_text, (400, y_pos))
                
                # Settings button
                btn_rect = pygame.Rect(600, y_pos, 150, 40)
                pygame.draw.rect(self.screen, self.colors['button'], btn_rect)
                btn_text = self.font_small.render("Settings", True, self.colors['text'])
                self.screen.blit(btn_text, (btn_rect.x + 10, btn_rect.y + 10))
            else:
                # No temperature data
                error_text = self.font_medium.render(f"{room}: No data", True, self.colors['inactive'])
                self.screen.blit(error_text, (50, y_pos))
                
                # Settings button
                btn_rect = pygame.Rect(600, y_pos, 150, 40)
                pygame.draw.rect(self.screen, self.colors['button'], btn_rect)
                btn_text = self.font_small.render("Settings", True, self.colors['text'])
                self.screen.blit(btn_text, (btn_rect.x + 10, btn_rect.y + 10))
            
            y_pos += 60
            
        # System status
        system_y = self.height - 60
        active_rooms = []
        for room, state in self.room_states.items():
            if state['cooling'] or state['heating']:
                active_rooms.append(room)
        
        if active_rooms:
            status_text = f"Active: {', '.join(active_rooms)}"
        else:
            status_text = "System Status: Idle"
        
        system_text = self.font_medium.render(status_text, True, self.colors['text'])
        self.screen.blit(system_text, (50, system_y))
        
    def draw_room_settings(self):
        self.screen.fill(self.colors['background'])
        
        if not self.selected_room:
            return
            
        room = self.selected_room
        temp = self.temperatures.get(room, 0)
        
        # Title
        title = self.font_large.render(f"{room} Settings", True, self.colors['text'])
        self.screen.blit(title, (20, 20))
        
        # Current temperature
        if temp is not None:
            temp_text = self.font_medium.render(f"Текущая: {temp:.1f}°C", True, self.colors['text'])
            self.screen.blit(temp_text, (20, 70))
        
        # Room status
        status_text = self.font_medium.render(f"Статус: {self.get_room_status_text(room)}", True, self.get_room_status_color(room))
        self.screen.blit(status_text, (20, 110))
        
        # Status indicator
        status_indicator_size = 20
        status_indicator = pygame.Rect(200, 115, status_indicator_size, status_indicator_size)
        pygame.draw.rect(self.screen, self.get_room_status_color(room), status_indicator)
        
        # Min temperature setting
        min_text = self.font_medium.render(f"Мин. темп.: {self.settings[room]['min_temp']}°C", True, self.colors['text'])
        self.screen.blit(min_text, (20, 160))
        
        # Min temp buttons
        min_up_btn = pygame.Rect(300, 160, 40, 40)
        min_down_btn = pygame.Rect(350, 160, 40, 40)
        
        pygame.draw.rect(self.screen, self.colors['button'], min_up_btn)
        pygame.draw.rect(self.screen, self.colors['button'], min_down_btn)
        
        self.screen.blit(self.font_medium.render("+", True, self.colors['text']), (min_up_btn.x + 15, min_up_btn.y + 10))
        self.screen.blit(self.font_medium.render("-", True, self.colors['text']), (min_down_btn.x + 15, min_down_btn.y + 10))
        
        # Max temperature setting
        max_text = self.font_medium.render(f"Макс. темп.: {self.settings[room]['max_temp']}°C", True, self.colors['text'])
        self.screen.blit(max_text, (20, 220))
        
        # Max temp buttons
        max_up_btn = pygame.Rect(300, 220, 40, 40)
        max_down_btn = pygame.Rect(350, 220, 40, 40)
        
        pygame.draw.rect(self.screen, self.colors['button'], max_up_btn)
        pygame.draw.rect(self.screen, self.colors['button'], max_down_btn)
        
        self.screen.blit(self.font_medium.render("+", True, self.colors['text']), (max_up_btn.x + 15, max_up_btn.y + 10))
        self.screen.blit(self.font_medium.render("-", True, self.colors['text']), (max_down_btn.x + 15, max_down_btn.y + 10))
        
        # Manual control buttons
        heat_btn = pygame.Rect(20, 280, 150, 60)
        cool_btn = pygame.Rect(200, 280, 150, 60)
        
        heat_color = self.colors['active'] if self.settings[room]['manual_heat'] else self.colors['button']
        cool_color = self.colors['active'] if self.settings[room]['manual_cool'] else self.colors['button']
        
        pygame.draw.rect(self.screen, heat_color, heat_btn)
        pygame.draw.rect(self.screen, cool_color, cool_btn)
        
        self.screen.blit(self.font_medium.render("Ручной обогрев", True, self.colors['text']), (heat_btn.x + 10, heat_btn.y + 20))
        self.screen.blit(self.font_medium.render("Ручное охлаждение", True, self.colors['text']), (cool_btn.x + 10, cool_btn.y + 20))
        
        # Back button
        back_btn = pygame.Rect(self.width - 170, self.height - 70, 150, 60)
        pygame.draw.rect(self.screen, (255, 100, 100), back_btn)
        back_text = self.font_medium.render("Назад", True, (255, 255, 255))
        self.screen.blit(back_text, (back_btn.x + 40, back_btn.y + 20))
        
    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
                
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE and self.current_screen == "settings":
                    self.current_screen = "main"
                    save_settings(self.settings)
                    return True
                    
            elif event.type == pygame.MOUSEBUTTONDOWN:
                pos = pygame.mouse.get_pos()
                
                if self.current_screen == "main":
                    # Check if any settings button was clicked
                    y_pos = 80
                    for room in sensor_ids.keys():
                        btn_rect = pygame.Rect(600, y_pos, 150, 40)
                        if btn_rect.collidepoint(pos):
                            self.selected_room = room
                            self.current_screen = "settings"
                            break
                        y_pos += 60
                        
                elif self.current_screen == "settings":
                    if not self.selected_room:
                        continue
                        
                    room = self.selected_room
                    
                    # Min temperature buttons
                    min_up_btn = pygame.Rect(300, 160, 40, 40)
                    min_down_btn = pygame.Rect(350, 160, 40, 40)
                    
                    if min_up_btn.collidepoint(pos):
                        self.settings[room]['min_temp'] += 1
                    elif min_down_btn.collidepoint(pos):
                        self.settings[room]['min_temp'] -= 1
                    
                    # Max temperature buttons
                    max_up_btn = pygame.Rect(300, 220, 40, 40)
                    max_down_btn = pygame.Rect(350, 220, 40, 40)
                    
                    if max_up_btn.collidepoint(pos):
                        self.settings[room]['max_temp'] += 1
                    elif max_down_btn.collidepoint(pos):
                        self.settings[room]['max_temp'] -= 1
                    
                    # Manual control buttons
                    heat_btn = pygame.Rect(20, 280, 150, 60)
                    cool_btn = pygame.Rect(200, 280, 150, 60)
                    
                    if heat_btn.collidepoint(pos):
                        self.settings[room]['manual_heat'] = not self.settings[room]['manual_heat']
                        if self.settings[room]['manual_heat']:
                            self.settings[room]['manual_cool'] = False
                    elif cool_btn.collidepoint(pos):
                        self.settings[room]['manual_cool'] = not self.settings[room]['manual_cool']
                        if self.settings[room]['manual_cool']:
                            self.settings[room]['manual_heat'] = False
                    
                    # Back button
                    back_btn = pygame.Rect(self.width - 170, self.height - 70, 150, 60)
                    if back_btn.collidepoint(pos):
                        self.current_screen = "main"
                        save_settings(self.settings)
        
        return True
        
    def update_temperatures(self):
        current_time = time.time()
        if current_time - self.last_temp_update >= 5:  # Update every 5 seconds
            for room, sensor_id in sensor_ids.items():
                self.temperatures[room] = read_temp(sensor_id)
            self.last_temp_update = current_time
            
    def control_climate(self):
        current_time = time.time()
        if current_time - self.last_control_update >= 10:  # Control every 10 seconds
            for room, sensor_id in sensor_ids.items():
                temp = self.temperatures.get(room)
                if temp is None:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Room {room}: No temperature data")
                    continue
                    
                min_temp = self.settings[room]['min_temp']
                max_temp = self.settings[room]['max_temp']
                
                # Manual control has priority
                if self.settings[room]['manual_heat']:
                    if not self.room_states[room]['heating']:
                        if (set_relay(room, True) and 
                            set_relay('heater_vent', True) and 
                            set_relay('supply', True)):
                            self.room_states[room]['heating'] = True
                            self.room_states[room]['cooling'] = False
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] Manual heating STARTED in {room}. Temperature: {temp:.2f}°C")
                
                elif self.settings[room]['manual_cool']:
                    if not self.room_states[room]['cooling']:
                        if set_relay(room, True) and set_relay('ac', True):
                            self.room_states[room]['cooling'] = True
                            self.room_states[room]['heating'] = False
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] Manual cooling STARTED in {room}. Temperature: {temp:.2f}°C")
                
                # Automatic control
                elif temp > max_temp and not self.room_states[room]['cooling']:
                    if set_relay(room, True) and set_relay('ac', True):
                        self.room_states[room]['cooling'] = True
                        self.room_states[room]['heating'] = False
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Cooling STARTED in {room}. Temperature: {temp:.2f}°C (Above {max_temp}°C)")
                    
                elif temp <= max_temp - 3 and self.room_states[room]['cooling']:
                    if set_relay(room, False):
                        self.room_states[room]['cooling'] = False
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Cooling STOPPED in {room}. Temperature: {temp:.2f}°C (Below {max_temp-3}°C)")
                    
                elif temp < min_temp and not self.room_states[room]['heating']:
                    if (set_relay(room, True) and 
                        set_relay('heater_vent', True) and 
                        set_relay('supply', True)):
                        self.room_states[room]['heating'] = True
                        self.room_states[room]['cooling'] = False
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Heating STARTED in {room}. Temperature: {temp:.2f}°C (Below {min_temp}°C)")
                    
                elif temp >= min_temp + 3 and self.room_states[room]['heating']:
                    if set_relay(room, False):
                        self.room_states[room]['heating'] = False
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Heating STOPPED in {room}. Temperature: {temp:.2f}°C (Above {min_temp+3}°C)")
            
            # Turn off AC if no room needs cooling
            if all(not state['cooling'] for state in self.room_states.values()):
                if set_relay('ac', False):
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] AC turned OFF (no room needs cooling)")
                
            # Turn off heater vent and supply if no room needs heating
            if all(not state['heating'] for state in self.room_states.values()):
                if set_relay('heater_vent', False):
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Heater vent turned OFF")
                if set_relay('supply', False):
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Supply turned OFF")
                
            self.last_control_update = current_time
            
    def run(self):
        running = True
        while running:
            running = self.handle_events()
            
            self.update_temperatures()
            self.control_climate()
            
            if self.current_screen == "main":
                self.draw_main_screen()
            elif self.current_screen == "settings":
                self.draw_room_settings()
                
            pygame.display.flip()
            self.clock.tick(30)
            
        # Cleanup
        save_settings(self.settings)
        # Turn off all relays on exit
        for name in relay_devices:
            set_relay(name, False)
        pygame.quit()

# Run the application
if __name__ == "__main__":
    app = ClimateControlApp()
    app.run()