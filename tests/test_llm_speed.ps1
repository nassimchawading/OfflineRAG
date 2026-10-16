# Part 2 test: ask a chat model one question and report speed + how much of it sits on the GPU.
# Ollama must be running (start_ollama.ps1).
# Usage:  .\tests\test_llm_speed.ps1 -Model qwen3:4b-instruct

param([string]$Model = "qwen3:4b-instruct")

$body = @{ model = $Model; think = $false; stream = $false
           prompt = "In 3 sentences: what is the difference between torque and power in an electric traction motor?" } | ConvertTo-Json
$r = Invoke-RestMethod http://127.0.0.1:11434/api/generate -Method Post -Body $body -ContentType "application/json" -TimeoutSec 300

"--- ANSWER ($Model) ---"; $r.response
"--- STATS ---"
"Load time:      {0:N1} s" -f ($r.load_duration / 1e9)
"Prompt reading: {0:N0} tokens/s" -f ($r.prompt_eval_count / ($r.prompt_eval_duration / 1e9))
"Answer speed:   {0:N1} tokens/s ({1} tokens)" -f ($r.eval_count / ($r.eval_duration / 1e9)), $r.eval_count
"Thinking leak:  " + ($(if ($r.response -match '</think>') { "YES (reasoning printed in answer)" } else { "no" }))
(Invoke-RestMethod http://127.0.0.1:11434/api/ps).models | Where-Object { $_.name -like "$Model*" } | ForEach-Object {
    "On GPU:         {0:N2} of {1:N2} GB ({2:P0}), context {3}" -f ($_.size_vram / 1GB), ($_.size / 1GB), ($_.size_vram / $_.size), $_.context_length }
