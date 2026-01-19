# Simple pylogger for Matcha-TTS compatibility
import logging

def get_pylogger(name=None):
    """Simple logger function for compatibility"""
    return logging.getLogger(name or __name__)
