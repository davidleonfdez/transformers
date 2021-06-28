# Copyright 2021 The HuggingFace Team. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from abc import ABC, abstractmethod
from typing import Any, Mapping, Optional

from transformers import PretrainedConfig, PreTrainedTokenizer, TensorType

from .utils import ParameterFormat, compute_effective_axis_dimension, compute_serialized_parameters_size


DEFAULT_ONNX_OPSET = 11

# 2 Gb
EXTERNAL_DATA_FORMAT_SIZE_LIMIT = 2 * 1024 * 1024 * 1024


DEFAULT_BERT_OPTIMIZER_FEATURES = {
    "enable_gelu": True,
    "enable_layer_norm": True,
    "enable_attention": True,
    "enable_skip_layer_norm": True,
    "enable_embed_layer_norm": True,
    "enable_bias_skip_layer_norm": True,
    "enable_bias_gelu": True,
    "enable_gelu_approximation": False,
}


class OnnxConfig(ABC):
    """
    Base class for ONNX exportable model describing metadata on how to export the model through the ONNX format.
    """

    def __init__(self, config: PretrainedConfig):
        self._config = config

    @classmethod
    def default(cls, config: PretrainedConfig) -> "OnnxConfig":
        """
        Instantiate a OnnxConfig for a specific model

        Args:
            config: The model's configuration to use when exporting to ONNX

        Returns:
            OnnxConfig for this model
        """
        return cls(config)

    @property
    @abstractmethod
    def inputs(self) -> Mapping[str, Mapping[int, str]]:
        """
        Mapping containing the axis definition of the input tensors to provide to the model

        Returns:
            For each input: its name associated to the axes symbolic name and the axis position within the tensor
        """
        raise NotImplementedError()

    @property
    @abstractmethod
    def outputs(self) -> Mapping[str, Mapping[int, str]]:
        """
        Mapping containing the axis definition of the output tensors to provide to the model

        Returns:
            For each output: its name associated to the axes symbolic name and the axis position within the tensor
        """
        raise NotImplementedError()

    @property
    def values_override(self) -> Optional[Mapping[str, Any]]:
        """
        Dictionary of keys to override in the model's config before exporting

        Returns:
            Dictionary with the keys (and their corresponding values) to override
        """
        if hasattr(self._config, "use_cache"):
            return {"use_cache": False}

        return None

    @property
    def default_onnx_opset(self) -> int:
        """
        Which onnx opset to use when exporting the model

        Returns:
            Integer ONNX Opset version
        """
        return DEFAULT_ONNX_OPSET

    @staticmethod
    def use_external_data_format(num_parameters: int) -> bool:
        """
        Flag indicating if the model requires using external data format

        Args:
            num_parameters: Number of parameter on the model

        Returns:
            True if model.num_parameters() * size_of(float32) >= 2Gb False otherwise
        """

        return (
            compute_serialized_parameters_size(num_parameters, ParameterFormat.Float)
            >= EXTERNAL_DATA_FORMAT_SIZE_LIMIT
        )

    def generate_dummy_inputs(
        self,
        tokenizer: PreTrainedTokenizer,
        batch_size: int = -1,
        seq_length: int = -1,
        is_pair: bool = False,
        framework: Optional[TensorType] = None,
    ) -> Mapping[str, Any]:
        """
        Generate inputs to provide to the ONNX exporter for the specific framework

        Args:
            tokenizer: The tokenizer associated with this model configuration
            batch_size: The batch size (int) to export the model for (-1 means dynamic axis)
            seq_length: The sequence length (int) to export the model for (-1 means dynamic axis)
            is_pair: Indicate if the input is a pair (sentence 1, sentence 2)
            framework: The framework (optional) the tokenizer will generate tensor for

        Returns:
            Mapping[str, Tensor] holding the kwargs to provide to the model's forward function
        """

        # If dynamic axis (-1) we forward with a fixed dimension of 2 samples to avoid optimizations made by ONNX
        batch_size = compute_effective_axis_dimension(batch_size, fixed_dimension=2, num_token_to_add=0)

        # If dynamic axis (-1) we forward with a fixed dimension of 8 tokens to avoid optimizations made by ONNX
        token_to_add = tokenizer.num_special_tokens_to_add(is_pair)
        seq_length = compute_effective_axis_dimension(seq_length, fixed_dimension=8, num_token_to_add=token_to_add)

        # Generate dummy inputs according to compute batch and sequence
        dummy_input = [" ".join([tokenizer.unk_token]) * seq_length] * batch_size
        return dict(tokenizer(dummy_input, return_tensors=framework))


class OnnxConfigWithPast(OnnxConfig, ABC):
    def __init__(self, config: PretrainedConfig, use_past: bool = False):
        super().__init__(config)
        self.use_past = use_past

    @classmethod
    def with_past(cls, config: PretrainedConfig) -> "OnnxConfig":
        """
        Instantiate a OnnxConfig with `use_past` attribute set to True

        Args:
            config: The underlying model's config to use when exporting to ONNX

        Returns:
            OnnxConfig with `.use_past = True`
        """
        return cls(config, use_past=True)

    @property
    def config_values_override(self) -> Optional[Mapping[str, Any]]:
        if hasattr(self._config, "use_cache"):
            return {"use_cache": self.use_past}

        return None
