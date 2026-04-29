#!/usr/bin/env python3
"""
Script to stop the OAuth2 callback server running on port 3021.
"""
import socket
import os
import sys
import time


def is_port_in_use(port):
    """Check if a port is in use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0


def stop_server(port=3021):
    """Stop the server running on the specified port."""
    if not is_port_in_use(port):
        print(f"✓ No server is running on port {port}")
        return True
    
    print(f"Stopping OAuth2 callback server on port {port}...")
    
    # Kill the process using the port
    result = os.system(f"lsof -ti:{port} | xargs kill -9 2>/dev/null")
    
    # Wait a moment for the process to terminate
    time.sleep(2)
    
    # Verify the port is now free
    if is_port_in_use(port):
        print(f"❌ Failed to stop server on port {port}")
        print(f"   Please manually kill the process:")
        print(f"   lsof -ti:{port} | xargs kill -9")
        return False
    
    print(f"✓ OAuth2 callback server stopped successfully")
    return True


if __name__ == "__main__":
    success = stop_server()
    sys.exit(0 if success else 1)
