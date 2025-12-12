#!/bin/bash
set -e

MODEL="llama3.2:3b"

echo "Starting Ollama server..."
ollama serve &

# 等待 server ready
echo "Waiting for Ollama server..."
until ollama list >/dev/null 2>&1; do
    sleep 2
done

# 拉模型（如果尚未拉過）
if ! ollama list | grep -q "$MODEL"; then
    echo "Pulling model $MODEL..."
    ollama pull $MODEL
fi

# 保持前景運行
wait
