# !/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
    [*] Description : Py3 wrapper for OpenAI LM models
    [*] Author      : dgeorgiou3@gmail.com
    [*] Date        : MAR2025
    [*] Links       :
"""

# -*-*-*-*-*-*-*-*-*-*-* #
#     Basic Modules      #
# -*-*-*-*-*-*-*-*-*-*-* #
import time
import threading
import concurrent.futures

from typing import Dict, Any, List, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor

# -*-*-*-*-*-*-*-*-*-*-* #
#   Third-Party Modules  #
# -*-*-*-*-*-*-*-*-*-*-* #
import openai
import tiktoken
from openai import OpenAI

class RateLimiter:
    """Token bucket rate limiter for API requests."""
    
    def __init__(self, tokens_per_second: float):
        """
        Initialize a rate limiter.
        
        Args:
            tokens_per_second (float): Tokens added per second
        """
        self.tokens_per_second = tokens_per_second
        self.token_bucket = 1.0  # Start with one token
        self.max_tokens = 1.0    # Maximum number of tokens
        self.last_update = time.time()
        self.lock = threading.Lock()
        
    def acquire(self):
        """
        Acquires a token from the bucket, blocking if necessary.
        """
        with self.lock:
            current_time = time.time()
            # Add tokens based on elapsed time
            time_elapsed = current_time - self.last_update
            new_tokens = time_elapsed * self.tokens_per_second
            self.token_bucket = min(self.max_tokens, self.token_bucket + new_tokens)
            self.last_update = current_time
            
            # If no tokens available, sleep until one is available
            if self.token_bucket < 1.0:
                sleep_time = (1.0 - self.token_bucket) / self.tokens_per_second
                time.sleep(sleep_time)
                self.token_bucket = 0.0
                self.last_update = time.time()
            else:
                self.token_bucket -= 1.0

class OpenaiAPI:
    def __init__(self, mk1, max_tokens=3000, temperature=0.3, max_workers=4):
        ## System Design
        self.mk1 = mk1
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.max_workers = max_workers

        ## __________ *** Initializing (attributes) *** _______
        self.token_key = str(self.mk1.config.get("api_openai", "token_key"))
        self.model_name = str(self.mk1.config.get("openai", "model_name"))

        ## __________ *** Initializing (client) *** __________
        self.service = self._build_client()

    # Service
    def _build_client(self):
        try:
            # Creating the OpenAI API client
            service = OpenAI(api_key = self.token_key)
            self.mk1.logging.logger.info(
                "(OpenaiAPI.build_client) Service build succeeded"
            )
            return service

        except Exception as e:
            self.mk1.logging.logger.error(
                f"(OpenaiAPI.build_client) Service build failed: {e}"
            )
            raise e
            return None

    def generate_summary(self, text: str, threshold: int = 7) -> List[str]:
        chunks = self._split_text(text)
        
        # Process in parallel
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            summaries = list(executor.map(self._summarize_chunk, chunks))
        
        # Filter by word count
        return [s for s in summaries if s and len(s.split()) >= threshold]
    
    def _split_text(self, text: str) -> List[str]:
        encoding = tiktoken.encoding_for_model(self.model_name)
        tokens = encoding.encode(text)
        
        chunks = []
        for i in range(0, len(tokens), self.max_tokens):
            chunk_tokens = tokens[i:i + self.max_tokens]
            chunk_text = encoding.decode(chunk_tokens)
            if chunk_text.strip():
                chunks.append(chunk_text)
        return chunks
    
    def _create_prompt(self, text: str) -> str:
        return f"""As a professional summarizer, create a concise summary following these rules:
            • Use English but keep original names/terms
            • Focus on essential information only
            • Write exactly 3 sentences in 1 paragraph
            • Maximum 30 words
            • Add 4 topic hashtags at the end
            • Include appropriate emojis
            • No formatting (bold/italic)

            Text: {text}"""
    
    def _summarize_chunk(self, text: str) -> Optional[str]:
        try:
            response = self.service.chat.completions.create(
                model       = self.model_name,
                messages    = [{"role": "user", "content": self._create_prompt(text)}],
                temperature = self.temperature,
                max_tokens  = 500,
                n           = 1
            )
            
            content = response.choices[0].message.content
            return content.strip() if content else None
            
        except openai.OpenAIError as e:
            self.mk1.logging.logger.error(f"(OpenaiAPI._summarize_chunk) Summary generation failed: {e}")
            return None
        except Exception as e:
            self.mk1.logging.logger.error(f"(OpenaiAPI._summarize_chunk) Unexpected error: {e}")
            return None
        
    def _fill_variables(self, text: str, variables: dict) -> str:
        """Fill variables in text using {variable_name} format."""
        if not text or not variables:
            return text or ""
        
        try:
            return text.format(**variables)
        except (KeyError, ValueError) as e:
            self.mk1.logging.logger.warning(f"(OpenaiAPI._fill_variables) Variable substitution failed: {e}")
            return text
            
    
    def execute_batch_custom_prompts(
            self, 
            prompts        : List[str], 
            variables_list : List[dict] = None,
            user_role      : str = None, 
            system_role    : str = None, 
            requirements   : List[str] = None, 
            examples       : List[dict] = None,
            max_tokens     : int = 500
        ) -> List[str]:
        """Execute multiple custom prompts in parallel."""
        if not prompts:
            return []
        
        args_list = [(
                prompts[i], 
                variables_list[i] if variables_list and i < len(variables_list) else {},
                user_role, 
                system_role, 
                requirements, 
                examples, 
                max_tokens
            ) 
            for i in range(len(prompts))
        ]
        
        with ThreadPoolExecutor(max_workers = self.max_workers) as executor:
            results = list(executor.map(self._execute_single, args_list))
        
        return [r for r in results if r is not None]
    
    def execute_custom_prompt(
            self, 
            prompt       : str, 
            variables    : dict = None, 
            user_role    : str = None, 
            system_role  : str = None, 
            requirements : List[str] = None, 
            examples     : List[dict] = None, 
            max_tokens   : int = 6000
        ) -> Optional[str]:
        """Execute custom prompt with variable substitution and role-based messaging."""
        try:
            # Fill variables
            if variables:
                prompt      = prompt.format(**variables) if prompt else prompt
                user_role   = user_role.format(**variables) if user_role else user_role
                system_role = system_role.format(**variables) if system_role else system_role
                requirements = [requirements.format(**variables) if requirements else requirements]

            messages = self._build_messages(
                prompt       = prompt, 
                user_role    = user_role, 
                system_role  = system_role, 
                requirements = requirements, 
                examples     = examples
            )
            
            response = self.service.chat.completions.create(
                model       = self.model_name, 
                messages    = messages, 
                temperature = self.temperature, 
                max_tokens  = max_tokens, 
                n           = 1
            )
            
            return response.choices[0].message.content.strip() if response.choices[0].message.content else None
            
        except Exception as e:
            raise e
            self.mk1.logging.logger.error(f"(OpenaiAPI.execute_custom_prompt) Custom prompt failed: {e}")
            return None
    
    def _execute_single(self, args: tuple) -> Optional[str]:
        """Helper for batch execution."""
        return self.execute_custom_prompt(*args)
    
    def _build_messages(
            self, 
            prompt       : str, 
            user_role    : str = None, 
            system_role  : str = None,
            requirements : List[str] = None, 
            examples     : List[dict] = None
        ) -> List[dict]:
        """Build message list for OpenAI API."""
        messages = []
        
        # System message
        system_parts = [system_role] if system_role else []
        if requirements:
            # system_parts.append("Requirements:\n" + "\n".join([f"• {req}" for req in requirements]))
            system_parts.append("Requirements:\n" + "\n".join(requirements))

        if examples:
            # system_parts.append("Examples:\n" + "\n\n".join([
            #     f"Input: {ex.get('input', '')}\nOutput: {ex.get('output', '')}" 
            #     for ex in examples
            # ]))
            system_parts.append("Examples:\n" + "\n".join(examples))
        
        if system_parts:
            messages.append({
                "role"    : "system", 
                "content" : "\n\n".join(system_parts)
            })
        
        # User message
        messages.append({
            "role"    : "user", 
            "content" : f"{user_role}\n\n{prompt}" if user_role else prompt
        })

        return messages
        
