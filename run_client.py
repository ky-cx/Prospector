#!/usr/bin/env python3
# prospector/run_client.py

import argparse
import logging
import sys
import os

# Add the parent directory to the path so we can import our modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from prospector.client.client import ProspectorClient
from prospector.common.constants import DEFAULT_HOST, DEFAULT_PORT

def main():
    """Main entry point for the Prospector client"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Prospector Game Client")
    parser.add_argument(
        "--host", 
        default=DEFAULT_HOST,
        help=f"Server host address (default: {DEFAULT_HOST})"
    )
    parser.add_argument(
        "--port", 
        type=int, 
        default=DEFAULT_PORT,
        help=f"Server port (default: {DEFAULT_PORT})"
    )
    parser.add_argument(
        "--log-level", 
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set the logging level (default: INFO)"
    )
    
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        filename='client.log'  # Log to file since stdout is used by curses
    )
    
    # Create and start client
    client = ProspectorClient(host=args.host, port=args.port)
    
    try:
        client.start()
    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        client.disconnect()

if __name__ == "__main__":
    main()