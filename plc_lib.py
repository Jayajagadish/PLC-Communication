#!/usr/bin/env python3
"""
Delta DVP10SX PLC Communication Library
UPDATED - Aligned with Actual PLC Program from PDF
"""

from pymodbus.client import ModbusSerialClient
from pymodbus import Framer
from pymodbus.exceptions import ModbusException
import logging
import time

logger = logging.getLogger(__name__)

class DeltaPLC:
    """Delta DVP10SX PLC Communication Class"""
    
    D_OFFSET = 0x1000  # D registers
    M_OFFSET = 0x0800  # M coils
    X_OFFSET = 0x0400  # X inputs
    Y_OFFSET = 0x0500  # Y outputs
    
    def __init__(self, config=None):
        if config is None:
            config = {
                'port': '/dev/ttyACM0',
                'baudrate': 9600,
                'bytesize': 7,
                'parity': 'E',
                'stopbits': 1,
                'timeout': 3,
                'slave_address': 1
            }
        self.config = config
        self.client = None
        self.connected = False
        
        # ========================================
        # ACTUAL PLC PROGRAM REGISTER MAPPING
        # Based on MODIFED-PLC-PROGRAM-FOR-RASPBERRY-PI-3.pdf
        # ========================================
        
        # X INPUTS (Physical Switches - READ ONLY)
        self.X_TRIGGER = 0      # X0 = Trigger
        self.X_AUTO = 1         # X1 = AUTO mode
        self.X_REMOTE = 2       # X2 = REMOTE mode
        self.X_INPUT_3 = 3      # X3 = Additional input
        
        # M COILS (Software Flags)
        self.M_FLAG_0 = 0       # M0 = Set by X0
        self.M_FLAG_1 = 1       # M1 = Set by X2 AND X1
        self.M_FLAG_2 = 2       # M2 = Set by X1 AND X2
        self.M_FLAG_3 = 3       # M3 = Set by X1 AND X2
        self.M_FLAG_4 = 4       # M4 = Set by X3
        self.M_D100_FLAG = 7    # M7 = Set when D100 >= 4 (line 153)
        self.M_TIMER_0 = 8      # M8 = Timer T0 state (line 61)
        self.M_TIMER_1 = 9      # M9 = Timer T1 state (line 76)
        
        # CRITICAL M COILS FOR OUTPUT CONTROL (lines 95-107)
        self.M_BLOWER_ENABLE = 100      # M100 = Blower enable
        self.M_BLOWER_INTERLOCK = 101   # M101 = Blower interlock
        self.M_VIBRO_ENABLE = 102       # M102 = Vibrofeeder enable
        self.M_VIBRO_INTERLOCK = 103    # M103 = Vibrofeeder interlock
        
        # Special relay
        self.M_ALWAYS_ON = 1000  # M1000 = Always ON (system flag)
        
        # Y OUTPUTS (Physical Devices)
        self.Y_BLOWER = 0       # Y0 = Blower motor (lines 48, 52, 56)
        self.Y_VIBRO = 1        # Y1 = Vibrofeeder motor (lines 65, 71)
        
        # D REGISTERS (Data Values) - From PLC Program
        self.D_SCALED_INPUT = 0     # D0 = SCLP operation result (line 11)
        self.D_PROCESS_VALUE = 1    # D1 = Moved to D1116 (line 81)
        self.D_INPUT_DATA_1 = 3     # D3 = Receives D1056 (line 3)
        self.D_INPUT_DATA_2 = 5     # D5 = Receives D1057 (line 123)
        self.D_CONST_1000 = 10      # D10 = Constant 1000 (line 17)
        self.D_CONST_200 = 11       # D11 = Constant 200 (line 20)
        self.D_CONST_20 = 12        # D12 = Constant 20 (line 23)
        self.D_CONST_4 = 13         # D13 = Constant 4 (line 26)
        self.D_DIV_RESULT = 30      # D30 = D1116/20 result (line 88)
        self.D_TIMER_VALUE = 50     # D50 = Timer control value (lines 43, 65)
        self.D_CONTROL_FLAG = 100   # D100 = Monitored flag (>=4 sets M7, line 153)
        self.D_TRANSFER_SRC = 1056  # D1056 = Source data (line 3)
        self.D_TRANSFER_SRC2 = 1057 # D1057 = Source data (line 123)
        self.D_CALC_BUFFER = 1116   # D1116 = Calculation buffer (lines 81, 88)
        
        # Safe registers for Raspberry Pi (not used by PLC program)
        self.D_RPI_SETPOINT = 200   # D200 = Safe write register
        self.D_RPI_COMMAND = 201    # D201 = Command register
        self.D_RPI_PARAM = 202      # D202 = Parameter register
    
    def connect(self):
        try:
            self.client = ModbusSerialClient(
                port=self.config['port'],
                framer=Framer.ASCII,
                baudrate=self.config['baudrate'],
                bytesize=self.config['bytesize'],
                parity=self.config['parity'],
                stopbits=self.config['stopbits'],
                timeout=self.config['timeout']
            )
            
            if self.client.connect():
                self.connected = True
                logger.info(f"Connected to PLC at {self.config['port']}")
                return True
            else:
                self.connected = False
                logger.error(f"Failed to connect to {self.config['port']}")
                return False
        except Exception as e:
            self.connected = False
            logger.error(f"Connection error: {e}")
            return False
    
    def disconnect(self):
        if self.client:
            self.client.close()
            self.connected = False
            logger.info("Disconnected from PLC")
    
    def ensure_connected(self):
        if not self.connected:
            return self.connect()
        return True
    
    def read_d_registers(self, start, count):
        if not self.ensure_connected():
            return None
        try:
            response = self.client.read_holding_registers(
                address=self.D_OFFSET + start,
                count=count,
                slave=self.config['slave_address']
            )
            if hasattr(response, 'registers'):
                return response.registers
            logger.error(f"Error reading D{start}: {response}")
            return None
        except Exception as e:
            logger.error(f"Exception reading D{start}: {e}")
            return None
    
    def read_m_coils(self, start, count):
        if not self.ensure_connected():
            return None
        try:
            response = self.client.read_coils(
                address=self.M_OFFSET + start,
                count=count,
                slave=self.config['slave_address']
            )
            if hasattr(response, 'bits'):
                return response.bits[:count]
            logger.error(f"Error reading M{start}: {response}")
            return None
        except Exception as e:
            logger.error(f"Exception reading M{start}: {e}")
            return None
    
    def read_x_inputs(self, start, count):
        if not self.ensure_connected():
            return None
        try:
            response = self.client.read_discrete_inputs(
                address=self.X_OFFSET + start,
                count=count,
                slave=self.config['slave_address']
            )
            if hasattr(response, 'bits'):
                return response.bits[:count]
            logger.error(f"Error reading X{start}: {response}")
            return None
        except Exception as e:
            logger.error(f"Exception reading X{start}: {e}")
            return None
    
    def read_y_outputs(self, start, count):
        if not self.ensure_connected():
            return None
        try:
            response = self.client.read_coils(
                address=self.Y_OFFSET + start,
                count=count,
                slave=self.config['slave_address']
            )
            if hasattr(response, 'bits'):
                return response.bits[:count]
            logger.error(f"Error reading Y{start}: {response}")
            return None
        except Exception as e:
            logger.error(f"Exception reading Y{start}: {e}")
            return None
    
    def write_d_register(self, address, value):
        if not self.ensure_connected():
            return False
        try:
            response = self.client.write_register(
                address=self.D_OFFSET + address,
                value=value,
                slave=self.config['slave_address']
            )
            if not response.isError():
                logger.info(f"Wrote D{address} = {value}")
                return True
            logger.error(f"Error writing D{address}: {response}")
            return False
        except Exception as e:
            logger.error(f"Exception writing D{address}: {e}")
            return False
    
    def write_m_coil(self, address, state):
        """Write M coil with verification"""
        if not self.ensure_connected():
            return False
        
        try:
            response = self.client.write_coils(
                address=self.M_OFFSET + address,
                values=[bool(state)],
                slave=self.config['slave_address']
            )
            
            if not response.isError():
                logger.info(f"Wrote M{address} = {'ON' if state else 'OFF'}")
                time.sleep(0.05)
                verify = self.read_m_coils(address, 1)
                if verify and verify[0] == state:
                    return True
                else:
                    logger.warning(f"M{address} write verification failed")
                    return self._write_m_coil_alt(address, state)
            
            logger.error(f"Error writing M{address}: {response}")
            return False
            
        except Exception as e:
            logger.error(f"Exception writing M{address}: {e}")
            return False
    
    def _write_m_coil_alt(self, address, state):
        """Alternative M coil write method"""
        try:
            response = self.client.write_coil(
                address=self.M_OFFSET + address,
                value=bool(state),
                slave=self.config['slave_address']
            )
            
            if not response.isError():
                logger.info(f"Wrote M{address} = {'ON' if state else 'OFF'} (alt method)")
                return True
            return False
        except:
            return False
    
    def write_y_output(self, address, state):
        if not self.ensure_connected():
            return False
        try:
            response = self.client.write_coil(
                address=self.Y_OFFSET + address,
                value=state,
                slave=self.config['slave_address']
            )
            if not response.isError():
                logger.info(f"Wrote Y{address} = {'ON' if state else 'OFF'}")
                return True
            logger.error(f"Error writing Y{address}: {response}")
            return False
        except Exception as e:
            logger.error(f"Exception writing Y{address}: {e}")
            return False
    
    def get_all_status(self):
        """Get complete PLC status"""
        from datetime import datetime
        data = {
            'timestamp': datetime.now().isoformat(),
            'connected': self.connected,
            'd_registers': {},
            'm_coils': {},
            'x_inputs': {},
            'y_outputs': {}
        }
        try:
            # Read D registers (0-10)
            d_values = self.read_d_registers(0, 10)
            if d_values:
                for i, val in enumerate(d_values):
                    data['d_registers'][f'D{i}'] = val
            
            # Read M coils (0-10)
            m_values = self.read_m_coils(0, 10)
            if m_values:
                for i, val in enumerate(m_values):
                    data['m_coils'][f'M{i}'] = bool(val)
            
            # Read X inputs (0-8)
            x_values = self.read_x_inputs(0, 8)
            if x_values:
                for i, val in enumerate(x_values):
                    data['x_inputs'][f'X{i}'] = bool(val)
            
            # Read Y outputs (0-8)
            y_values = self.read_y_outputs(0, 8)
            if y_values:
                for i, val in enumerate(y_values):
                    data['y_outputs'][f'Y{i}'] = bool(val)
            
            return data
        except Exception as e:
            logger.error(f"Error getting status: {e}")
            return None
