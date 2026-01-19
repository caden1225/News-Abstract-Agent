# Simple xutils for Matcha-TTS HiFiGAN compatibility
import torch
import torch.nn as nn

def get_padding(kernel_size, dilation=1):
    """Calculate padding for convolution"""
    return int((kernel_size * dilation - dilation) / 2)

def init_weights(m, mean=0.0, std=0.01):
    """Initialize weights"""
    if isinstance(m, nn.Conv1d):
        m.weight.data.normal_(mean, std)
