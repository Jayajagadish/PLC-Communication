#!/usr/bin/env python3
"""
Delta DVP10SX PLC - REST API Server
UPDATED - Adds M100-M103 support for complete ladder logic exposure
"""

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from plc_lib import DeltaPLC
import logging
import json
import sys
import os
from pathlib import Path

# Setup logging
log_file = Path.home() / 'plc_api.log'
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
CORS(app)  # Enable CORS for web dashboard

# Initialize PLC connection (singleton - only one instance)
plc = DeltaPLC()

# ==================== HEALTH CHECK ====================

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'running',
        'plc_connected': plc.connected,
        'api_version': '1.0.0'
    }), 200

# ==================== PLC STATUS ====================

@app.route('/api/status', methods=['GET'])
def get_status():
    """Get complete PLC status including M100-M103"""
    try:
        status = plc.get_all_status()
        if status:
            # CRITICAL: Add M100-M103 to M coils
            m100_103 = plc.read_m_coils(100, 4)
            if m100_103:
                status['m_coils']['M100'] = bool(m100_103[0])
                status['m_coils']['M101'] = bool(m100_103[1])
                status['m_coils']['M102'] = bool(m100_103[2])
                status['m_coils']['M103'] = bool(m100_103[3])
            
            return jsonify(status), 200
        else:
            return jsonify({
                'error': 'Failed to read PLC',
                'connected': plc.connected
            }), 500
    except Exception as e:
        logger.error(f"Status error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/status/summary', methods=['GET'])
def get_status_summary():
    """Get summary of active items only"""
    try:
        status = plc.get_all_status()
        if not status:
            return jsonify({'error': 'Failed to read PLC'}), 500
        
        # Add M100-M103
        m100_103 = plc.read_m_coils(100, 4)
        if m100_103:
            status['m_coils']['M100'] = bool(m100_103[0])
            status['m_coils']['M101'] = bool(m100_103[1])
            status['m_coils']['M102'] = bool(m100_103[2])
            status['m_coils']['M103'] = bool(m100_103[3])
        
        # Filter to show only active/non-zero items
        summary = {
            'timestamp': status['timestamp'],
            'connected': status['connected'],
            'm_coils_on': [k for k, v in status['m_coils'].items() if v],
            'y_outputs_on': [k for k, v in status['y_outputs'].items() if v],
            'x_inputs_on': [k for k, v in status['x_inputs'].items() if v],
            'd_registers_nonzero': {k: v for k, v in status['d_registers'].items() if v != 0}
        }
        
        return jsonify(summary), 200
        
    except Exception as e:
        logger.error(f"Summary error: {e}")
        return jsonify({'error': str(e)}), 500

# ==================== D REGISTERS ====================

@app.route('/api/d/<int:address>', methods=['GET', 'POST'])
def d_register(address):
    """Read or write D register"""
    try:
        if request.method == 'GET':
            # Read single register
            values = plc.read_d_registers(address, 1)
            if values is not None:
                return jsonify({
                    'success': True,
                    'address': f'D{address}',
                    'value': values[0]
                }), 200
            else:
                return jsonify({
                    'error': f'Failed to read D{address}',
                    'connected': plc.connected
                }), 500
        
        elif request.method == 'POST':
            # Write register
            data = request.get_json()
            value = int(data.get('value', 0))
            
            if not (0 <= value <= 65535):
                return jsonify({'error': 'Value must be 0-65535'}), 400
            
            if plc.write_d_register(address, value):
                return jsonify({
                    'success': True,
                    'address': f'D{address}',
                    'value': value
                }), 200
            else:
                return jsonify({
                    'error': f'Failed to write D{address}',
                    'connected': plc.connected
                }), 500
                
    except ValueError as e:
        return jsonify({'error': f'Invalid value: {e}'}), 400
    except Exception as e:
        logger.error(f"D register error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/d/range/<int:start>/<int:count>', methods=['GET'])
def d_register_range(start, count):
    """Read multiple D registers"""
    try:
        if count > 100:
            return jsonify({'error': 'Maximum 100 registers per request'}), 400
        
        values = plc.read_d_registers(start, count)
        if values is not None:
            result = {f'D{start + i}': val for i, val in enumerate(values)}
            return jsonify({
                'success': True,
                'start': start,
                'count': count,
                'registers': result
            }), 200
        else:
            return jsonify({'error': 'Failed to read registers'}), 500
            
    except Exception as e:
        logger.error(f"D register range error: {e}")
        return jsonify({'error': str(e)}), 500

# ==================== M COILS ====================

@app.route('/api/m/<int:address>', methods=['GET', 'POST'])
def m_coil(address):
    """Read or write M coil (including M100-M103)"""
    try:
        if request.method == 'GET':
            # Read single coil
            values = plc.read_m_coils(address, 1)
            if values is not None:
                return jsonify({
                    'success': True,
                    'address': f'M{address}',
                    'state': bool(values[0])
                }), 200
            else:
                return jsonify({
                    'error': f'Failed to read M{address}',
                    'connected': plc.connected
                }), 500
        
        elif request.method == 'POST':
            # Write coil
            data = request.get_json()
            state = bool(data.get('state', False))
            
            if plc.write_m_coil(address, state):
                return jsonify({
                    'success': True,
                    'address': f'M{address}',
                    'state': state
                }), 200
            else:
                return jsonify({
                    'error': f'Failed to write M{address}',
                    'connected': plc.connected
                }), 500
                
    except Exception as e:
        logger.error(f"M coil error: {e}")
        return jsonify({'error': str(e)}), 500

# ==================== Y OUTPUTS ====================

@app.route('/api/y/<int:address>', methods=['GET', 'POST'])
def y_output(address):
    """Read or write Y output"""
    try:
        if request.method == 'GET':
            # Read single output
            values = plc.read_y_outputs(address, 1)
            if values is not None:
                return jsonify({
                    'success': True,
                    'address': f'Y{address}',
                    'state': bool(values[0])
                }), 200
            else:
                return jsonify({
                    'error': f'Failed to read Y{address}',
                    'connected': plc.connected
                }), 500
        
        elif request.method == 'POST':
            # Write output
            data = request.get_json()
            state = bool(data.get('state', False))
            
            if plc.write_y_output(address, state):
                return jsonify({
                    'success': True,
                    'address': f'Y{address}',
                    'state': state
                }), 200
            else:
                return jsonify({
                    'error': f'Failed to write Y{address}',
                    'connected': plc.connected
                }), 500
                
    except Exception as e:
        logger.error(f"Y output error: {e}")
        return jsonify({'error': str(e)}), 500

# ==================== X INPUTS (READ-ONLY) ====================

@app.route('/api/x/<int:address>', methods=['GET'])
def x_input(address):
    """Read X input (read-only)"""
    try:
        values = plc.read_x_inputs(address, 1)
        if values is not None:
            return jsonify({
                'success': True,
                'address': f'X{address}',
                'state': bool(values[0])
            }), 200
        else:
            return jsonify({
                'error': f'Failed to read X{address}',
                'connected': plc.connected
            }), 500
    except Exception as e:
        logger.error(f"X input error: {e}")
        return jsonify({'error': str(e)}), 500

# ==================== CONNECTION MANAGEMENT ====================

@app.route('/api/connect', methods=['POST'])
def connect():
    """Connect to PLC"""
    try:
        if plc.connect():
            return jsonify({
                'success': True,
                'message': 'Connected to PLC'
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to connect'
            }), 500
    except Exception as e:
        logger.error(f"Connect error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/disconnect', methods=['POST'])
def disconnect():
    """Disconnect from PLC"""
    try:
        plc.disconnect()
        return jsonify({
            'success': True,
            'message': 'Disconnected from PLC'
        }), 200
    except Exception as e:
        logger.error(f"Disconnect error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/reconnect', methods=['POST'])
def reconnect():
    """Reconnect to PLC"""
    try:
        plc.disconnect()
        if plc.connect():
            return jsonify({
                'success': True,
                'message': 'Reconnected to PLC'
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to reconnect'
            }), 500
    except Exception as e:
        logger.error(f"Reconnect error: {e}")
        return jsonify({'error': str(e)}), 500

# ==================== BULK OPERATIONS ====================

@app.route('/api/bulk/m', methods=['POST'])
def bulk_write_m():
    """Write multiple M coils at once"""
    try:
        data = request.get_json()
        coils = data.get('coils', {})  # {'0': true, '3': false, ...}
        
        results = {}
        success_count = 0
        
        for address_str, state in coils.items():
            address = int(address_str)
            success = plc.write_m_coil(address, bool(state))
            results[f'M{address}'] = success
            if success:
                success_count += 1
        
        return jsonify({
            'success': success_count == len(coils),
            'total': len(coils),
            'succeeded': success_count,
            'results': results
        }), 200
        
    except Exception as e:
        logger.error(f"Bulk M write error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/bulk/y', methods=['POST'])
def bulk_write_y():
    """Write multiple Y outputs at once"""
    try:
        data = request.get_json()
        outputs = data.get('outputs', {})
        
        results = {}
        success_count = 0
        
        for address_str, state in outputs.items():
            address = int(address_str)
            success = plc.write_y_output(address, bool(state))
            results[f'Y{address}'] = success
            if success:
                success_count += 1
        
        return jsonify({
            'success': success_count == len(outputs),
            'total': len(outputs),
            'succeeded': success_count,
            'results': results
        }), 200
        
    except Exception as e:
        logger.error(f"Bulk Y write error: {e}")
        return jsonify({'error': str(e)}), 500

# ==================== STATIC FILES ====================

@app.route('/')
def index():
    """Serve main dashboard"""
    try:
        return send_from_directory('.', 'plc_dashboard.html')
    except:
        return jsonify({
            'message': 'PLC API Server Running',
            'endpoints': {
                'status': '/api/status',
                'summary': '/api/status/summary',
                'health': '/health'
            }
        }), 200

@app.route('/<path:path>')
def serve_static(path):
    """Serve static files"""
    try:
        return send_from_directory('.', path)
    except:
        return jsonify({'error': 'File not found'}), 404

# ==================== ERROR HANDLERS ====================

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

# ==================== STARTUP ====================

def check_port_available(port=5000):
    """Check if port is available"""
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('127.0.0.1', port))
    sock.close()
    return result != 0

if __name__ == '__main__':
    logger.info("Starting PLC API Server...")
    
    # Check if port is available
    if not check_port_available(5000):
        logger.error("Port 5000 is already in use!")
        logger.error("Either stop the existing server or change the port")
        logger.error("To stop existing server: sudo fuser -k 5000/tcp")
        sys.exit(1)
    
    # Connect to PLC on startup
    if plc.connect():
        logger.info("PLC connected successfully")
    else:
        logger.warning("PLC connection failed - will retry on first request")
    
    # Print access information
    import socket
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    
    logger.info("=" * 60)
    logger.info(f"PLC API Server Started")
    logger.info(f"Local access:   http://127.0.0.1:5000")
    logger.info(f"Network access: http://{local_ip}:5000")
    logger.info(f"Dashboard:      http://{local_ip}:5000/")
    logger.info(f"Health check:   http://{local_ip}:5000/health")
    logger.info(f"Status API:     http://{local_ip}:5000/api/status")
    logger.info(f"Log file:       {log_file}")
    logger.info("=" * 60)
    
    # Run Flask server
    # For production, use: gunicorn -w 4 -b 0.0.0.0:5000 plc_api:app
    try:
        app.run(
            host='0.0.0.0',      # Listen on all interfaces
            port=5000,
            debug=False,         # Set to False in production
            threaded=True,       # Handle multiple requests
            use_reloader=False   # Disable auto-reload in production
        )
    except KeyboardInterrupt:
        logger.info("\nShutting down...")
        plc.disconnect()
        logger.info("Server stopped")
    except Exception as e:
        logger.error(f"Server error: {e}")
        sys.exit(1)
