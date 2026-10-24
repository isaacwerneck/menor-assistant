<#
.SYNOPSIS
    Script de configuração e download automatizado do Ollama no PC Windows (GPU GTX 1650).
.DESCRIPTION
    Instala o Ollama via winget, configura permissão de CORS (OLLAMA_ORIGINS="*"),
    inicia o serviço e baixa o modelo ultra-rápido otimizado para a GTX 1650 (qwen2.5:3b / 7b).
#>

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = "Stop"

Write-Host "`n========================================================" -ForegroundColor Cyan
Write-Host "   🚀 Menor v2 — Configuração do Ollama no PC Windows" -ForegroundColor Cyan
Write-Host "========================================================`n" -ForegroundColor Cyan

# 1. Verificar se Ollama já está instalado
$ollamaCmd = Get-Command "ollama" -ErrorAction SilentlyContinue

if (-not $ollamaCmd) {
    Write-Host "[1/4] Ollama não encontrado. Baixando e instalando via winget..." -ForegroundColor Yellow
    try {
        winget install Ollama.Ollama --accept-source-agreements --accept-package-agreements --silent
        Write-Host "✔ Ollama instalado com sucesso!" -ForegroundColor Green
        
        # Atualizar PATH na sessão atual
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
    } catch {
        Write-Host "❌ Falha ao instalar via winget. Tentando instalador direto..." -ForegroundColor Red
        $installerUrl = "https://ollama.com/download/OllamaSetup.exe"
        $installerPath = "$env:TEMP\OllamaSetup.exe"
        Invoke-WebRequest -Uri $installerUrl -OutFile $installerPath
        Start-Process -FilePath $installerPath -Wait
        Write-Host "✔ Instalador executado." -ForegroundColor Green
    }
} else {
    Write-Host "[1/4] ✔ Ollama já está instalado em: $($ollamaCmd.Source)" -ForegroundColor Green
}

# 2. Configurar CORS (OLLAMA_ORIGINS="*") para permitir conexões do navegador do Menor v2
Write-Host "`n[2/4] Configurando CORS no Windows (OLLAMA_ORIGINS='*')..." -ForegroundColor Yellow
[System.Environment]::SetEnvironmentVariable('OLLAMA_ORIGINS', '*', 'User')
[System.Environment]::SetEnvironmentVariable('OLLAMA_HOST', '0.0.0.0:11434', 'User')
$env:OLLAMA_ORIGINS = "*"
$env:OLLAMA_HOST = "0.0.0.0:11434"
Write-Host "✔ Variáveis de ambiente configuradas com sucesso." -ForegroundColor Green

# 3. Garantir que o processo do Ollama está rodando
Write-Host "`n[3/4] Verificando serviço do Ollama..." -ForegroundColor Yellow
$proc = Get-Process "ollama" -ErrorAction SilentlyContinue
if (-not $proc) {
    Write-Host "Iniciando Ollama em segundo plano..." -ForegroundColor Yellow
    Start-Process "ollama" -ArgumentList "serve" -WindowStyle Hidden
    Start-Sleep -Seconds 3
} else {
    Write-Host "✔ Processo do Ollama já está em execução." -ForegroundColor Green
}

# 4. Baixar o modelo ideal para a GPU GTX 1650 (4 GB VRAM)
Write-Host "`n[4/4] Baixando o modelo rápido qwen2.5:3b (ultra-rápido, ~45 tokens/s na GPU)..." -ForegroundColor Yellow
Write-Host "Aguarde o download dos pesos do modelo (~1.9 GB)..." -ForegroundColor Cyan

ollama pull qwen2.5:3b

Write-Host "`n========================================================" -ForegroundColor Green
Write-Host "🎉 CONCLUÍDO! Ollama e modelo configurados com sucesso!" -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Green
Write-Host "O site do Menor v2 já pode se conectar diretamente ao seu PC:" -ForegroundColor White
Write-Host "• No chat, selecione 'PC Local (GPU) - 7B/3B' no canto superior direito." -ForegroundColor White
Write-Host "• Ou ative o '🎙️ Modo Voz Contínua' para conversar hands-free instantaneamente!" -ForegroundColor White
Write-Host "`nPara testar agora no terminal: ollama run qwen2.5:3b`n" -ForegroundColor Cyan
