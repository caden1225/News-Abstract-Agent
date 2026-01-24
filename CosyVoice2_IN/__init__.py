"""
CosyVoice2 集成包入口

- 直接导出 CosyVoice2 与 load_wav，供 `from cosyvoice2 import CosyVoice2, load_wav` 使用
- 为 hyperpyyaml 提供模块别名，使得配置中的字符串路径
  （如 "cosyvoice.llm.llm.Qwen2LM"、"matcha.models.components.flow_matching" 等）可被正确解析
"""

# 先创建代理模块结构，避免 hyperpyyaml 解析字符串类路径失败
import sys
from types import ModuleType


def _make_proxy_modules():
    # 需要被 hyperpyyaml 解析到的模块名（以 cosyvoice / matcha 开头）
    cosyvoice_modules = [
        'cosyvoice',
        'cosyvoice.cli',
        'cosyvoice.llm',
        'cosyvoice.flow',
        'cosyvoice.transformer',
        'cosyvoice.utils',
        'cosyvoice.hifigan',
    ]

    matcha_modules = [
        'matcha',
        'matcha.models',
        'matcha.models.components',
        'matcha.hifigan',
        'matcha.utils',
    ]

    for name in cosyvoice_modules + matcha_modules:
        if name not in sys.modules:
            sys.modules[name] = ModuleType(name)


_make_proxy_modules()

# 导入真实顶层包，并优先将顶层名绑定为真实包，确保其有 __path__
from . import cosyvoice as _cosyvoice_pkg, matcha as _matcha_pkg
sys.modules['cosyvoice'] = _cosyvoice_pkg
sys.modules['matcha'] = _matcha_pkg

# 预先将 matcha 的关键子包绑定为真实包，避免后续导入时命中占位模块
# 注意：必须按照依赖顺序导入和绑定，flow_matching 依赖 matcha.utils.pylogger
from .matcha import models as _m_models_pkg, utils as _m_utils_pkg
sys.modules['matcha.models'] = _m_models_pkg
sys.modules['matcha.utils'] = _m_utils_pkg  # 必须提前绑定，因为 flow_matching 会导入 matcha.utils.pylogger
from .matcha.models import components as _m_components_pkg
sys.modules['matcha.models.components'] = _m_components_pkg

# 再导入需要的对象与子模块
from .cosyvoice.cli.cosyvoice import CosyVoice2
from .cosyvoice.utils.file_utils import load_wav

from .cosyvoice import cli as _cv_cli, llm as _cv_llm, flow as _cv_flow, transformer as _cv_transformer, utils as _cv_utils, hifigan as _cv_hifigan
from .cosyvoice.llm import llm as _cv_llm_module
from .cosyvoice.flow import flow as _cv_flow_module
from .cosyvoice.transformer import upsample_encoder as _cv_upsample_encoder
from .cosyvoice.utils import common as _cv_utils_common
from .cosyvoice.hifigan import generator as _cv_hifigan_generator

from .matcha import models as _m_models, hifigan as _m_hifigan, utils as _m_utils
from .matcha.models import components as _m_components
# 在确保 'matcha.models'、'matcha.models.components' 和 'matcha.utils' 都已绑定为真实包后再导入其子模块
from .matcha.models.components import decoder as _m_decoder, flow_matching as _m_flow_matching, transformer as _m_transformer

# 绑定其余常用子模块名
sys.modules['cosyvoice.cli'] = _cv_cli
sys.modules['cosyvoice.llm'] = _cv_llm
sys.modules['cosyvoice.llm.llm'] = _cv_llm_module
sys.modules['cosyvoice.flow'] = _cv_flow
sys.modules['cosyvoice.flow.flow'] = _cv_flow_module
sys.modules['cosyvoice.transformer'] = _cv_transformer
sys.modules['cosyvoice.transformer.upsample_encoder'] = _cv_upsample_encoder
sys.modules['cosyvoice.utils'] = _cv_utils
sys.modules['cosyvoice.utils.common'] = _cv_utils_common
sys.modules['cosyvoice.hifigan'] = _cv_hifigan
sys.modules['cosyvoice.hifigan.generator'] = _cv_hifigan_generator

sys.modules['matcha.models'] = _m_models
sys.modules['matcha.models.components'] = _m_components
sys.modules['matcha.models.components.flow_matching'] = _m_flow_matching
sys.modules['matcha.models.components.decoder'] = _m_decoder
sys.modules['matcha.models.components.transformer'] = _m_transformer
sys.modules['matcha.hifigan'] = _m_hifigan
sys.modules['matcha.utils'] = _m_utils


__all__ = [
    "CosyVoice2",
    "load_wav",
]

