# Starts the Ollama server for this project. Keep this window open while you use the chatbot;
# close it (or press Ctrl+C) to stop Ollama and free the GPU.
#
# Run it from PowerShell:   .\start_ollama.ps1
#
# The two settings below only apply to this window. Nothing is changed permanently in Windows.

# Store models inside the project folder instead of C:\Users\<you>\.ollama
$env:OLLAMA_MODELS = Join-Path $PSScriptRoot "models"
# Only accept connections from this laptop (not from other devices on the network)
$env:OLLAMA_HOST = "127.0.0.1:11434"
# Skip Vulkan GPU detection: it hangs on this laptop, and the RTX 3050 uses CUDA anyway
$env:OLLAMA_VULKAN = "0"
# Store the model's working memory (KV cache) at half size so more of the model fits on the 4 GB GPU.
# Flash attention is required for this and is also faster.
$env:OLLAMA_FLASH_ATTENTION = "1"
$env:OLLAMA_KV_CACHE_TYPE = "q8_0"

New-Item -ItemType Directory -Force $env:OLLAMA_MODELS | Out-Null
Write-Host "Starting Ollama. Models folder: $env:OLLAMA_MODELS"
& (Join-Path $PSScriptRoot "tools\ollama\ollama.exe") serve
