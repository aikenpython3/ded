import pygame
import gpiod
import time
import os
import json
import sys
from datetime import datetime

# GPIO configuration
CHIP_NAME = 'gpiochip4'
RELAY_PINS = {
    'ac': 27, 'heater_vent': 28, 'room3': 29, 'room2': 31,
    'room1': 37, 'supply': 33, 'room4': 35, 'room5': 36
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

# Initialize GPIO
chip = None
line_requests = {}

try:
    chip = gpiod.Chip(CHIP_NAME)
    for name, pin in RELAY_PINS.items():
        line = chip.get_line(pin)
        line.request(consumer=f"climate_{name}", type=gpiod.LINE_REQ_DIR_OUT)
        line_requests[pin] = line
        line.set_value(1)  # OFF state
except Exception as e:
    print(f"Error initializing GPIO: {e}")

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
def set_relay(pin, state):
    try:
        line = line_requests[pin]
        line.set_value(0 if state else 1)  # 0=ON, 1=OFF
        return True
    except:
        print(f"Error controlling relay on pin {pin}")
        return False

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
        
    def draw_main_screen(self):
        self.screen.fill(self.colors['background'])
        
        # Title
        title = self.font_large.render("Climate Control System", True, self.colors['text'])
        self.screen.blit(title, (20, 20))
        
        # Time
        time_text = self.font_medium.render(datetime.now().strftime('%Y-%m-%d %H:%M:%S'), True, self.colors['text'])
        self.screen.blit(time_text, (self.width - time_text.get_width() - 20, 20))
        
        # Room temperatures
        y_pos = 80
        for room, temp in self.temperatures.items():
            if temp is not None:
                # Determine color based on temperature
                if temp > self.settings[room]['max_temp']:
                    color = self.colors['hot']
                elif temp < self.settings[room]['min_temp']:
                    color = self.colors['cold']
                else:
                    color = self.colors['normal']
                
                # Room temperature
                temp_text = self.font_medium.render(f"{room}: {temp:.1f}°C", True, color)
                self.screen.blit(temp_text, (50, y_pos))
                
                # Status indicators
                if self.room_states[room]['cooling']:
                    status = self.font_small.render("Cooling", True, self.colors['active'])
                    self.screen.blit(status, (250, y_pos))
                elif self.room_states[room]['heating']:
                    status = self.font_small.render("Heating", True, self.colors['active'])
                    self.screen.blit(status, (250, y_pos))
                
                # Settings button
                btn_rect = pygame.Rect(600, y_pos, 150, 40)
                pygame.draw.rect(self.screen, self.colors['button'], btn_rect)
                btn_text = self.font_small.render("Settings", True, self.colors['text'])
                self.screen.blit(btn_text, (btn_rect.x + 10, btn_rect.y + 10))
                
            y_pos += 60
            
        # System status
        system_y = self.height - 60
        system_text = self.font_medium.render("System Status: OK", True, self.colors['text'])
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
            temp_text = self.font_medium.render(f"Current: {temp:.1f}°C", True, self.colors['text'])
            self.screen.blit(temp_text, (20, 70))
        
        # Min temperature setting
        min_text = self.font_medium.render(f"Min Temp: {self.settings[room]['min_temp']}°C", True, self.colors['text'])
        self.screen.blit(min_text, (20, 120))
        
        # Min temp buttons
        min_up_btn = pygame.Rect(300, 120, 40, 40)
        min_down_btn = pygame.Rect(350, 120, 40, 40)
        
        pygame.draw.rect(self.screen, self.colors['button'], min_up_btn)
        pygame.draw.rect(self.screen, self.colors['button'], min_down_btn)
        
        self.screen.blit(self.font_medium.render("+", True, self.colors['text']), (min_up_btn.x + 15, min_up_btn.y + 10))
        self.screen.blit(self.font_medium.render("-", True, self.colors['text']), (min_down_btn.x + 15, min_down_btn.y + 10))
        
        # Max temperature setting
        max_text = self.font_medium.render(f"Max Temp: {self.settings[room]['max_temp']}°C", True, self.colors['text'])
        self.screen.blit(max_text, (20, 180))
        
        # Max temp buttons
        max_up_btn = pygame.Rect(300, 180, 40, 40)
        max_down_btn = pygame.Rect(350, 180, 40, 40)
        
        pygame.draw.rect(self.screen, self.colors['button'], max_up_btn)
        pygame.draw.rect(self.screen, self.colors['button'], max_down_btn)
        
        self.screen.blit(self.font_medium.render("+", True, self.colors['text']), (max_up_btn.x + 15, max_up_btn.y + 10))
        self.screen.blit(self.font_medium.render("-", True, self.colors['text']), (max_down_btn.x + 15, max_down_btn.y + 10))
        
        # Manual control buttons
        heat_btn = pygame.Rect(20, 240, 150, 60)
        cool_btn = pygame.Rect(200, 240, 150, 60)
        
        heat_color = self.colors['active'] if self.settings[room]['manual_heat'] else self.colors['button']
        cool_color = self.colors['active'] if self.settings[room]['manual_cool'] else self.colors['button']
        
        pygame.draw.rect(self.screen, heat_color, heat_btn)
        pygame.draw.rect(self.screen, cool_color, cool_btn)
        
        self.screen.blit(self.font_medium.render("Manual Heat", True, self.colors['text']), (heat_btn.x + 10, heat_btn.y + 20))
        self.screen.blit(self.font_medium.render("Manual Cool", True, self.colors['text']), (cool_btn.x + 10, cool_btn.y + 20))
        
        # Back button
        back_btn = pygame.Rect(self.width - 170, self.height - 70, 150, 60)
        pygame.draw.rect(self.screen, self.colors['button'], back_btn)
        self.screen.blit(self.font_medium.render("Back", True, self.colors['text']), (back_btn.x + 40, back_btn.y + 20))
        
    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
                
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
                    min_up_btn = pygame.Rect(300, 120, 40, 40)
                    min_down_btn = pygame.Rect(350, 120, 40, 40)
                    
                    if min_up_btn.collidepoint(pos):
                        self.settings[room]['min_temp'] += 1
                    elif min_down_btn.collidepoint(pos):
                        self.settings[room]['min_temp'] -= 1
                    
                    # Max temperature buttons
                    max_up_btn = pygame.Rect(300, 180, 40, 40)
                    max_down_btn = pygame.Rect(350, 180, 40, 40)
                    
                    if max_up_btn.collidepoint(pos):
                        self.settings[room]['max_temp'] += 1
                    elif max_down_btn.collidepoint(pos):
                        self.settings[room]['max_temp'] -= 1
                    
                    # Manual control buttons
                    heat_btn = pygame.Rect(20, 240, 150, 60)
                    cool_btn = pygame.Rect(200, 240, 150, 60)
                    
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
                    continue
                    
                relay_pin = RELAY_PINS[room]
                min_temp = self.settings[room]['min_temp']
                max_temp = self.settings[room]['max_temp']
                
                # Manual control has priority
                if self.settings[room]['manual_heat']:
                    if not self.room_states[room]['heating']:
                        if (set_relay(relay_pin, True) and 
                            set_relay(RELAY_PINS['heater_vent'], True) and 
                            set_relay(RELAY_PINS['supply'], True)):
                            self.room_states[room]['heating'] = True
                            self.room_states[room]['cooling'] = False
                
                elif self.settings[room]['manual_cool']:
                    if not self.room_states[room]['cooling']:
                        if set_relay(relay_pin, True) and set_relay(RELAY_PINS['ac'], True):
                            self.room_states[room]['cooling'] = True
                            self.room_states[room]['heating'] = False
                
                # Automatic control
                elif temp > max_temp and not self.room_states[room]['cooling']:
                    if set_relay(relay_pin, True) and set_relay(RELAY_PINS['ac'], True):
                        self.room_states[room]['cooling'] = True
                        self.room_states[room]['heating'] = False
                    
                elif temp <= max_temp - 3 and self.room_states[room]['cooling']:
                    if set_relay(relay_pin, False):
                        self.room_states[room]['cooling'] = False
                    
                elif temp < min_temp and not self.room_states[room]['heating']:
                    if (set_relay(relay_pin, True) and 
                        set_relay(RELAY_PINS['heater_vent'], True) and 
                        set_relay(RELAY_PINS['supply'], True)):
                        self.room_states[room]['heating'] = True
                        self.room_states[room]['cooling'] = False
                    
                elif temp >= min_temp + 3 and self.room_states[room]['heating']:
                    if set_relay(relay_pin, False):
                        self.room_states[room]['heating'] = False
            
            # Turn off AC if no room needs cooling
            if all(not state['cooling'] for state in self.room_states.values()):
                set_relay(RELAY_PINS['ac'], False)
                
            # Turn off heater vent and supply if no room needs heating
            if all(not state['heating'] for state in self.room_states.values()):
                set_relay(RELAY_PINS['heater_vent'], False)
                set_relay(RELAY_PINS['supply'], False)
                
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
        for pin, line in line_requests.items():
            try:
                line.set_value(1)  # Set to OFF state
                line.release()
            except:
                pass
        if chip:
            chip.close()
        pygame.quit()

# Run the application
if __name__ == "__main__":
    app = ClimateControlApp()
    app.run()