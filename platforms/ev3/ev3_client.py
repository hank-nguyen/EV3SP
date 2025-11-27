#!/usr/bin/env python3
"""
EV3 Streaming Client
--------------------
Runs on EV3 Brick to stream sensor/motor data to host machine.
Uses ev3dev Python bindings.
"""

import json
import socket
import sys
import time
import threading
from typing import Optional

# ev3dev2 imports (available on ev3dev image)
try:
    from ev3dev2.motor import Motor, OUTPUT_A, OUTPUT_B, OUTPUT_C, OUTPUT_D
    from ev3dev2.sensor import INPUT_1, INPUT_2, INPUT_3, INPUT_4
    from ev3dev2.sensor.lego import TouchSensor, ColorSensor, UltrasonicSensor, GyroSensor
    EV3DEV_AVAILABLE = True
except ImportError:
    EV3DEV_AVAILABLE = False
    print("Warning: ev3dev2 not available, running in mock mode")


class EV3StreamingServer:
    """Streaming server that runs on EV3 to send sensor/motor data."""
    
    DEFAULT_PORT = 9999
    
    MOTOR_PORTS = {
        'A': OUTPUT_A if EV3DEV_AVAILABLE else None,
        'B': OUTPUT_B if EV3DEV_AVAILABLE else None,
        'C': OUTPUT_C if EV3DEV_AVAILABLE else None,
        'D': OUTPUT_D if EV3DEV_AVAILABLE else None,
    }
    
    SENSOR_PORTS = {
        'S1': INPUT_1 if EV3DEV_AVAILABLE else None,
        'S2': INPUT_2 if EV3DEV_AVAILABLE else None,
        'S3': INPUT_3 if EV3DEV_AVAILABLE else None,
        'S4': INPUT_4 if EV3DEV_AVAILABLE else None,
    }
    
    def __init__(self, port: int = DEFAULT_PORT):
        self.port = port
        self._running = False
        self._server_socket: Optional[socket.socket] = None
        self._motors: dict = {}
        self._sensors: dict = {}
        self._detect_devices()
    
    def _detect_devices(self) -> None:
        """Detect connected motors and sensors."""
        if not EV3DEV_AVAILABLE:
            return
        
        # Detect motors
        for name, port in self.MOTOR_PORTS.items():
            try:
                motor = Motor(port)
                self._motors[name] = motor
                print(f"✓ Motor detected on port {name}: {motor.driver_name}")
            except Exception:
                pass
        
        # Detect sensors with type checking
        sensor_classes = [
            ('touch', TouchSensor),
            ('color', ColorSensor),
            ('ultrasonic', UltrasonicSensor),
            ('gyro', GyroSensor),
        ]
        
        for name, port in self.SENSOR_PORTS.items():
            for sensor_type, sensor_class in sensor_classes:
                try:
                    sensor = sensor_class(port)
                    self._sensors[name] = {'type': sensor_type, 'sensor': sensor}
                    print(f"✓ {sensor_type.capitalize()} sensor on port {name}")
                    break
                except Exception:
                    continue
    
    def get_state(self) -> dict:
        """Get current state of all motors and sensors."""
        state = {
            'timestamp': time.time(),
            'motors': {},
            'sensors': {}
        }
        
        # Read motors
        for name, motor in self._motors.items():
            try:
                state['motors'][name] = {
                    'position': motor.position,
                    'speed': motor.speed,
                    'state': motor.state,
                }
            except Exception as e:
                state['motors'][name] = {'error': str(e)}
        
        # Read sensors
        for name, sensor_info in self._sensors.items():
            try:
                sensor = sensor_info['sensor']
                sensor_type = sensor_info['type']
                
                if sensor_type == 'touch':
                    value = sensor.is_pressed
                elif sensor_type == 'color':
                    value = {
                        'color': sensor.color_name,
                        'ambient': sensor.ambient_light_intensity,
                        'reflected': sensor.reflected_light_intensity,
                    }
                elif sensor_type == 'ultrasonic':
                    value = sensor.distance_centimeters
                elif sensor_type == 'gyro':
                    value = {
                        'angle': sensor.angle,
                        'rate': sensor.rate,
                    }
                else:
                    value = sensor.value()
                
                state['sensors'][name] = {
                    'type': sensor_type,
                    'value': value
                }
            except Exception as e:
                state['sensors'][name] = {'type': sensor_type, 'error': str(e)}
        
        return state
    
    def handle_command(self, cmd: dict) -> dict:
        """Handle incoming command from host."""
        action = cmd.get('action')
        response = {'success': False, 'action': action}
        
        try:
            if action == 'motor':
                port = cmd.get('port', 'A')
                if port in self._motors:
                    motor = self._motors[port]
                    speed = cmd.get('speed', 0)
                    duration = cmd.get('duration')
                    position = cmd.get('position')
                    
                    if position is not None:
                        motor.on_to_position(speed, position)
                    elif duration is not None:
                        motor.on_for_seconds(speed, duration / 1000.0)
                    elif speed == 0:
                        motor.stop()
                    else:
                        motor.on(speed)
                    
                    response['success'] = True
                else:
                    response['error'] = f'Motor {port} not connected'
            
            elif action == 'stop_motor':
                port = cmd.get('port', 'A')
                if port in self._motors:
                    self._motors[port].stop()
                    response['success'] = True
                else:
                    response['error'] = f'Motor {port} not connected'
            
            elif action == 'read_sensor':
                port = cmd.get('port', 'S1')
                if port in self._sensors:
                    sensor_info = self._sensors[port]
                    sensor = sensor_info['sensor']
                    response['value'] = sensor.value()
                    response['success'] = True
                else:
                    response['error'] = f'Sensor {port} not connected'
            
            elif action == 'get_state':
                response['state'] = self.get_state()
                response['success'] = True
            
            elif action == 'list_devices':
                response['motors'] = list(self._motors.keys())
                response['sensors'] = {k: v['type'] for k, v in self._sensors.items()}
                response['success'] = True
            
            else:
                response['error'] = f'Unknown action: {action}'
        
        except Exception as e:
            response['error'] = str(e)
        
        return response
    
    def start(self) -> None:
        """Start the streaming server."""
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_socket.bind(('0.0.0.0', self.port))
        self._server_socket.listen(1)
        self._running = True
        
        print(f"EV3 Streaming Server started on port {self.port}")
        print("Waiting for connection...")
        
        while self._running:
            try:
                self._server_socket.settimeout(1.0)
                try:
                    client_socket, addr = self._server_socket.accept()
                except socket.timeout:
                    continue
                
                print(f"Client connected: {addr}")
                self._handle_client(client_socket)
                
            except KeyboardInterrupt:
                print("\nShutting down...")
                break
            except Exception as e:
                print(f"Error: {e}")
        
        self.stop()
    
    def _handle_client(self, client_socket: socket.socket) -> None:
        """Handle a connected client."""
        client_socket.settimeout(0.1)
        streaming = False
        stream_interval = 0.1
        last_stream = 0
        
        try:
            while self._running:
                # Check for incoming commands
                try:
                    data = client_socket.recv(4096)
                    if not data:
                        break
                    
                    # Parse command(s)
                    for line in data.decode().strip().split('\n'):
                        if not line:
                            continue
                        cmd = json.loads(line)
                        
                        if cmd.get('action') == 'start_stream':
                            streaming = True
                            stream_interval = cmd.get('interval', 100) / 1000.0
                            print(f"Streaming started (interval={stream_interval*1000}ms)")
                        elif cmd.get('action') == 'stop_stream':
                            streaming = False
                            print("Streaming stopped")
                        else:
                            response = self.handle_command(cmd)
                            client_socket.send((json.dumps(response) + '\n').encode())
                
                except socket.timeout:
                    pass
                except json.JSONDecodeError as e:
                    print(f"JSON error: {e}")
                
                # Stream state if enabled
                if streaming and time.time() - last_stream >= stream_interval:
                    state = self.get_state()
                    try:
                        client_socket.send((json.dumps(state) + '\n').encode())
                        last_stream = time.time()
                    except BrokenPipeError:
                        break
        
        except Exception as e:
            print(f"Client error: {e}")
        finally:
            client_socket.close()
            print("Client disconnected")
    
    def stop(self) -> None:
        """Stop the server."""
        self._running = False
        if self._server_socket:
            self._server_socket.close()
        print("Server stopped")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="EV3 Streaming Server")
    parser.add_argument('--port', type=int, default=EV3StreamingServer.DEFAULT_PORT,
                       help='Server port')
    parser.add_argument('--test', action='store_true',
                       help='Print state once and exit (for testing)')
    args = parser.parse_args()
    
    server = EV3StreamingServer(port=args.port)
    
    if args.test:
        print("Detected devices:")
        print(f"  Motors: {list(server._motors.keys())}")
        print(f"  Sensors: {list(server._sensors.keys())}")
        print("\nCurrent state:")
        print(json.dumps(server.get_state(), indent=2))
    else:
        server.start()


if __name__ == "__main__":
    main()

