"""
数据集处理模块（占位符）

这些函数在推理时不需要，但CosyVoice3的配置文件会引用它们。
为了支持配置文件加载，这里提供占位符函数。
"""


def parquet_opener(*args, **kwargs):
    """占位符函数，用于配置文件解析"""
    raise NotImplementedError("parquet_opener is only used during training, not inference")


def tokenize(*args, **kwargs):
    """占位符函数，用于配置文件解析"""
    raise NotImplementedError("tokenize is only used during training, not inference")


def filter(*args, **kwargs):
    """占位符函数，用于配置文件解析"""
    raise NotImplementedError("filter is only used during training, not inference")


def resample(*args, **kwargs):
    """占位符函数，用于配置文件解析"""
    raise NotImplementedError("resample is only used during training, not inference")


def truncate(*args, **kwargs):
    """占位符函数，用于配置文件解析"""
    raise NotImplementedError("truncate is only used during training, not inference")


def compute_fbank(*args, **kwargs):
    """占位符函数，用于配置文件解析"""
    raise NotImplementedError("compute_fbank is only used during training, not inference")


def compute_f0(*args, **kwargs):
    """占位符函数，用于配置文件解析"""
    raise NotImplementedError("compute_f0 is only used during training, not inference")


def parse_embedding(*args, **kwargs):
    """占位符函数，用于配置文件解析"""
    raise NotImplementedError("parse_embedding is only used during training, not inference")


def shuffle(*args, **kwargs):
    """占位符函数，用于配置文件解析"""
    raise NotImplementedError("shuffle is only used during training, not inference")


def sort(*args, **kwargs):
    """占位符函数，用于配置文件解析"""
    raise NotImplementedError("sort is only used during training, not inference")


def batch(*args, **kwargs):
    """占位符函数，用于配置文件解析"""
    raise NotImplementedError("batch is only used during training, not inference")


def padding(*args, **kwargs):
    """占位符函数，用于配置文件解析"""
    raise NotImplementedError("padding is only used during training, not inference")

