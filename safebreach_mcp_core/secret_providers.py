'''
Secret provider interface and implementations for the SafeBreach MCP server.

This module provides an extensible architecture for retrieving secrets from
different storage backends (AWS SSM, AWS Secrets Manager, etc.).
'''

from abc import ABC, abstractmethod
from typing import Dict, Any
import boto3
from botocore.exceptions import ClientError
import logging
import os

logger = logging.getLogger(__name__)


class SecretProvider(ABC):
    """Abstract base class for secret providers."""
    
    @abstractmethod
    def get_secret(self, secret_identifier: str) -> str:
        """
        Retrieve a secret value.
        
        Args:
            secret_identifier: The identifier for the secret (parameter name, secret name, etc.)
            
        Returns:
            The secret value as a string
            
        Raises:
            Exception: If the secret cannot be retrieved
        """
        pass


class AWSSSMSecretProvider(SecretProvider):
    """AWS Systems Manager Parameter Store secret provider."""
    
    def __init__(self, region_name: str = 'us-east-1'):
        """
        Initialize the AWS SSM secret provider.
        
        Args:
            region_name: AWS region name (default: us-east-1)
        """
        self.region_name = region_name
        self._client = None
        self._cache: Dict[str, str] = {}
    
    @property
    def client(self):
        """Lazy initialization of boto3 client."""
        if self._client is None:
            self._client = boto3.client('ssm', region_name=self.region_name)
        return self._client
    
    def get_secret(self, parameter_name: str) -> str:
        """
        Get a parameter from AWS SSM Parameter Store.
        
        Args:
            parameter_name: The parameter name in SSM
            
        Returns:
            The parameter value
            
        Raises:
            ClientError: If the parameter cannot be retrieved
        """
        if parameter_name in self._cache:
            logger.debug(f"Retrieved cached SSM parameter: {parameter_name}")
            return self._cache[parameter_name]
        
        try:
            logger.info(f"Retrieving SSM parameter: {parameter_name}")
            response = self.client.get_parameter(
                Name=parameter_name,
                WithDecryption=True
            )
            value = response['Parameter']['Value']
            self._cache[parameter_name] = value
            logger.debug(f"Successfully retrieved SSM parameter: {parameter_name}")
            return value
        except ClientError as e:
            logger.error(f"Failed to retrieve SSM parameter {parameter_name}: {e}")
            raise


class AWSSecretsManagerProvider(SecretProvider):
    """AWS Secrets Manager secret provider."""
    
    def __init__(self, region_name: str = 'us-east-1'):
        """
        Initialize the AWS Secrets Manager secret provider.
        
        Args:
            region_name: AWS region name (default: us-east-1)
        """
        self.region_name = region_name
        self._client = None
        self._cache: Dict[str, str] = {}
    
    @property
    def client(self):
        """Lazy initialization of boto3 client."""
        if self._client is None:
            session = boto3.Session()
            self._client = session.client(
                service_name='secretsmanager',
                region_name=self.region_name
            )
        return self._client
    
    def get_secret(self, secret_name: str) -> str:
        """
        Get a secret from AWS Secrets Manager.
        
        Args:
            secret_name: The secret name in Secrets Manager
            
        Returns:
            The secret value
            
        Raises:
            ClientError: If the secret cannot be retrieved
        """
        if secret_name in self._cache:
            logger.debug(f"Retrieved cached Secrets Manager secret: {secret_name}")
            return self._cache[secret_name]
        
        try:
            logger.info(f"Retrieving Secrets Manager secret: {secret_name}")
            response = self.client.get_secret_value(SecretId=secret_name)
            value = response['SecretString']
            self._cache[secret_name] = value
            logger.debug(f"Successfully retrieved Secrets Manager secret: {secret_name}")
            return value
        except ClientError as e:
            logger.error(f"Failed to retrieve Secrets Manager secret {secret_name}: {e}")
            raise


class EnvVarSecretProvider(SecretProvider):
    """Environment variable secret provider."""
    
    def __init__(self):
        """Initialize the environment variable secret provider."""
        self._cache: Dict[str, str] = {}
    
    def get_secret(self, env_var_name: str) -> str:
        """
        Get a secret from environment variables.
        
        Args:
            env_var_name: The environment variable name
            
        Returns:
            The environment variable value
            
        Raises:
            ValueError: If the environment variable is not found or empty
        """
        if env_var_name in self._cache:
            logger.debug(f"Retrieved cached environment variable: {env_var_name}")
            return self._cache[env_var_name]
        
        logger.info(f"Retrieving environment variable: {env_var_name}")
        value = os.getenv(env_var_name.replace('-', '_'))
        
        if value is None:
            error_msg = f"Environment variable '{env_var_name}' not found"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        if not value.strip():
            error_msg = f"Environment variable '{env_var_name}' is empty"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        self._cache[env_var_name] = value
        logger.debug(f"Successfully retrieved environment variable: {env_var_name}")
        return value


class SecretProviderFactory:
    """Factory for creating secret providers."""
    
    _providers = {
        'aws_ssm': AWSSSMSecretProvider,
        'aws_secrets_manager': AWSSecretsManagerProvider,
        'env_var': EnvVarSecretProvider,
    }
    
    @classmethod
    def create_provider(cls, provider_type: str, **kwargs) -> SecretProvider:
        """
        Create a secret provider instance.
        
        Args:
            provider_type: Type of provider ('aws_ssm', 'aws_secrets_manager', 'env_var')
            **kwargs: Additional arguments for provider initialization
            
        Returns:
            SecretProvider instance
            
        Raises:
            ValueError: If provider_type is not supported
        """
        if provider_type not in cls._providers:
            raise ValueError(f"Unsupported provider type: {provider_type}. "
                           f"Supported types: {list(cls._providers.keys())}")
        
        provider_class = cls._providers[provider_type]
        return provider_class(**kwargs)
    
    @classmethod
    def get_supported_providers(cls) -> list:
        """Get list of supported provider types."""
        return list(cls._providers.keys())