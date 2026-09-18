param(
  [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,
  [string]$LogFile = ''
)

$ErrorActionPreference = 'Stop'
$Root = [System.IO.Path]::GetFullPath($Root)
if ([string]::IsNullOrWhiteSpace($LogFile)) {
  $LogFile = Join-Path $Root 'log.txt'
}
$LogFile = [System.IO.Path]::GetFullPath($LogFile)

function Write-OraculoLog {
  param([string]$Line)

  $texto = if ($null -eq $Line) { '' } else { $Line }
  for ($tentativa = 1; $tentativa -le 10; $tentativa++) {
    try {
      Add-Content -LiteralPath $LogFile -Value $texto -Encoding UTF8
      break
    } catch {
      if ($tentativa -eq 10) { throw }
      Start-Sleep -Milliseconds 80
    }
  }
  Write-Host $texto
}

function Test-PortaLivre {
  param([int]$Porta)

  $conn = Get-NetTCPConnection -State Listen -LocalPort $Porta -ErrorAction SilentlyContinue
  return $null -eq $conn
}

function Start-ProcessoComLog {
  param(
    [string]$Nome,
    [string]$Arquivo,
    [string[]]$Argumentos,
    [string]$Diretorio
  )

  $psi = [System.Diagnostics.ProcessStartInfo]::new()
  $psi.FileName = $Arquivo
  foreach ($arg in $Argumentos) {
    [void]$psi.ArgumentList.Add($arg)
  }
  $psi.WorkingDirectory = $Diretorio
  $psi.UseShellExecute = $false
  $psi.RedirectStandardOutput = $true
  $psi.RedirectStandardError = $true
  $psi.CreateNoWindow = $true

  $proc = [System.Diagnostics.Process]::new()
  $proc.StartInfo = $psi
  $proc.EnableRaisingEvents = $true

  $stdout = {
    if (-not [string]::IsNullOrWhiteSpace($EventArgs.Data)) {
      $meta = $Event.MessageData
      $linha = "[{0}] {1}" -f $meta.Nome, $EventArgs.Data
      for ($tentativa = 1; $tentativa -le 10; $tentativa++) {
        try {
          Add-Content -LiteralPath $meta.LogFile -Value $linha -Encoding UTF8
          break
        } catch {
          if ($tentativa -eq 10) { throw }
          Start-Sleep -Milliseconds 80
        }
      }
      Write-Host $linha
    }
  }
  $stderr = {
    if (-not [string]::IsNullOrWhiteSpace($EventArgs.Data)) {
      $meta = $Event.MessageData
      $linha = "[{0}:ERRO] {1}" -f $meta.Nome, $EventArgs.Data
      for ($tentativa = 1; $tentativa -le 10; $tentativa++) {
        try {
          Add-Content -LiteralPath $meta.LogFile -Value $linha -Encoding UTF8
          break
        } catch {
          if ($tentativa -eq 10) { throw }
          Start-Sleep -Milliseconds 80
        }
      }
      Write-Host $linha
    }
  }

  [void]$proc.Start()
  $meta = @{ Nome = $Nome; LogFile = $LogFile }
  Register-ObjectEvent -InputObject $proc -EventName OutputDataReceived -Action $stdout -MessageData $meta | Out-Null
  Register-ObjectEvent -InputObject $proc -EventName ErrorDataReceived -Action $stderr -MessageData $meta | Out-Null
  $proc.BeginOutputReadLine()
  $proc.BeginErrorReadLine()
  Write-OraculoLog ("[{0}] processo iniciado pid={1}" -f $Nome, $proc.Id)
  return $proc
}

Set-Location -LiteralPath $Root

Write-OraculoLog ''
Write-OraculoLog '============================================================'
Write-OraculoLog ("[START] {0} - iniciando Oraculo" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))
Write-OraculoLog ("[START] diretorio={0}" -f $Root)
Write-OraculoLog ("[START] log={0}" -f $LogFile)
Write-OraculoLog '============================================================'

$python = Join-Path $Root '.venv\Scripts\python.exe'
$venvActivate = Join-Path $Root '.venv\Scripts\activate.bat'
$frontend = Join-Path $Root 'frontend'

if (-not (Test-Path -LiteralPath $venvActivate)) {
  Write-OraculoLog '[ERRO] Venv nao encontrada em .venv.'
  exit 1
}
if (-not (Test-Path -LiteralPath $python)) {
  Write-OraculoLog '[ERRO] Python da venv nao encontrado em .venv\Scripts\python.exe.'
  exit 1
}
if (-not (Test-Path -LiteralPath $frontend)) {
  Write-OraculoLog '[ERRO] Diretorio frontend nao encontrado.'
  exit 1
}

if (-not (Test-Path -LiteralPath (Join-Path $frontend 'node_modules'))) {
  Write-OraculoLog '[INFO] Instalando dependencias do frontend...'
  $npm = Start-ProcessoComLog -Nome 'NPM' -Arquivo 'cmd.exe' -Argumentos @('/c', 'npm install') -Diretorio $frontend
  $npm.WaitForExit()
  if ($npm.ExitCode -ne 0) {
    Write-OraculoLog ("[ERRO] npm install falhou exit_code={0}" -f $npm.ExitCode)
    exit $npm.ExitCode
  }
}

Write-OraculoLog '[INFO] Iniciando backend e frontend...'
$backend = $null
$front = $null

if (Test-PortaLivre 8000) {
  $backend = Start-ProcessoComLog -Nome 'BACKEND' -Arquivo $python -Argumentos @('-u', 'src\main.py') -Diretorio $Root
} else {
  $pidPorta = (Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object -First 1).OwningProcess
  Write-OraculoLog ("[INFO] Backend ja esta ativo na porta 8000. Nao vou iniciar duplicado. pid={0}" -f $pidPorta)
}

if (Test-PortaLivre 3000) {
  $front = Start-ProcessoComLog -Nome 'FRONTEND' -Arquivo 'node.exe' -Argumentos @('server.js') -Diretorio $frontend
} else {
  $pidPorta = (Get-NetTCPConnection -State Listen -LocalPort 3000 -ErrorAction SilentlyContinue | Select-Object -First 1).OwningProcess
  Write-OraculoLog ("[INFO] Frontend ja esta ativo na porta 3000. Nao vou iniciar duplicado. pid={0}" -f $pidPorta)
}

if (-not $backend -and -not $front) {
  Write-OraculoLog '[OK] Backend e frontend ja estavam ativos.'
  exit 0
}

Write-OraculoLog '[OK] Backend:  http://127.0.0.1:8000'
Write-OraculoLog '[OK] Frontend: http://127.0.0.1:3000'
Write-OraculoLog '[INFO] Mantenha esta janela aberta. Fechar esta janela interrompe backend/frontend.'

try {
  while ($true) {
    if ($backend -and $backend.HasExited) {
      Write-OraculoLog ("[ERRO] Backend encerrou exit_code={0}" -f $backend.ExitCode)
      break
    }
    if ($front -and $front.HasExited) {
      Write-OraculoLog ("[ERRO] Frontend encerrou exit_code={0}" -f $front.ExitCode)
      break
    }
    Start-Sleep -Seconds 2
  }
} finally {
  foreach ($proc in @($backend, $front)) {
    if ($proc -and -not $proc.HasExited) {
      try {
        $proc.Kill()
      } catch {
      }
    }
  }
}
