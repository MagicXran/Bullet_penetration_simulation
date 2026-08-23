const fs = require('fs');
const filePath = 'C:/Users/ZDxia/.claude/plugins/marketplaces/thedotmack/src/shared/worker-utils.ts';

let content = fs.readFileSync(filePath, 'utf-8');
const lines = content.split('\n');

// Find line numbers for insertion points
let insertBeforeStartWorker = -1;
let ensureWorkerRunningStart = -1;
let ensureWorkerRunningEnd = -1;

for (let i = 0; i < lines.length; i++) {
  if (lines[i].includes('Start the worker service using ProcessManager')) {
    insertBeforeStartWorker = i - 1; // Line before the /** comment
  }
  if (lines[i].includes('Ensure worker service is running')) {
    ensureWorkerRunningStart = i - 1; // Line before the /** comment
  }
}

// Find the end of ensureWorkerRunning function (last closing brace at indentation level 0)
if (ensureWorkerRunningStart !== -1) {
  let braceCount = 0;
  let inFunction = false;
  for (let i = ensureWorkerRunningStart; i < lines.length; i++) {
    if (lines[i].includes('export async function ensureWorkerRunning')) {
      inFunction = true;
    }
    if (inFunction) {
      braceCount += (lines[i].match(/{/g) || []).length;
      braceCount -= (lines[i].match(/}/g) || []).length;
      if (braceCount === 0 && inFunction && lines[i].trim() === '}') {
        ensureWorkerRunningEnd = i;
        break;
      }
    }
  }
}

console.log('Insert lock functions before line:', insertBeforeStartWorker + 1);
console.log('ensureWorkerRunning: lines', ensureWorkerRunningStart + 1, 'to', ensureWorkerRunningEnd + 1);

if (insertBeforeStartWorker === -1 || ensureWorkerRunningStart === -1 || ensureWorkerRunningEnd === -1) {
  console.log('Could not find insertion points');
  process.exit(1);
}

const lockFunctions = `/**
 * 获取锁文件路径
 */
function getLockFilePath(): string {
  return path.join(SettingsDefaultsManager.get('CLAUDE_MEM_DATA_DIR'), 'worker.lock');
}

/**
 * 尝试获取文件锁（防止多 session 同时启动 worker）
 */
function acquireLock(): boolean {
  try {
    const dataDir = SettingsDefaultsManager.get('CLAUDE_MEM_DATA_DIR');
    mkdirSync(dataDir, { recursive: true });

    const lockFile = getLockFilePath();

    // 检查是否有现有锁
    if (existsSync(lockFile)) {
      try {
        const lockData = JSON.parse(readFileSync(lockFile, 'utf-8'));
        const lockAge = Date.now() - lockData.timestamp;

        // 如果锁超时，删除它
        if (lockAge > LOCK_TIMEOUT_MS) {
          logger.debug('SYSTEM', 'Removing stale lock file', { lockAge });
          unlinkSync(lockFile);
        } else {
          return false; // 锁仍然有效
        }
      } catch {
        // 锁文件损坏，删除它
        try { unlinkSync(lockFile); } catch {}
      }
    }

    // 创建锁
    writeFileSync(lockFile, JSON.stringify({
      timestamp: Date.now(),
      pid: process.pid
    }));

    return true;
  } catch (error) {
    logger.debug('SYSTEM', 'Failed to acquire lock', { error: error instanceof Error ? error.message : String(error) });
    return false;
  }
}

/**
 * 释放文件锁
 */
function releaseLock(): void {
  try {
    const lockFile = getLockFilePath();
    if (existsSync(lockFile)) {
      unlinkSync(lockFile);
    }
  } catch {
    // 忽略错误
  }
}

`;

const newEnsureWorkerRunning = `/**
 * Ensure worker service is running
 * Checks health and auto-starts if not running
 * Also ensures worker version matches plugin version
 * 使用文件锁防止多 session 同时启动 worker
 */
export async function ensureWorkerRunning(): Promise<void> {
  // Check if already healthy
  if (await isWorkerHealthy()) {
    // Worker is healthy, but check if version matches
    await ensureWorkerVersionMatches();
    return;
  }

  // 尝试获取锁
  const maxRetries = 10;
  let lockAcquired = false;

  for (let i = 0; i < maxRetries; i++) {
    if (acquireLock()) {
      lockAcquired = true;
      break;
    }
    // 等待一段时间后重试
    await new Promise(resolve => setTimeout(resolve, 500));

    // 在等待期间再次检查 worker 是否已经启动
    if (await isWorkerHealthy()) {
      await ensureWorkerVersionMatches();
      return;
    }
  }

  if (!lockAcquired) {
    // 无法获取锁，但 worker 可能已经在启动中，等待更长时间
    logger.debug('SYSTEM', 'Could not acquire lock, waiting for worker to start');
    for (let i = 0; i < 10; i++) {
      await new Promise(resolve => setTimeout(resolve, 1000));
      if (await isWorkerHealthy()) {
        await ensureWorkerVersionMatches();
        return;
      }
    }
    throw new Error('Could not acquire lock to start worker and worker is not responding');
  }

  try {
    // 再次检查（可能在获取锁期间已启动）
    if (await isWorkerHealthy()) {
      await ensureWorkerVersionMatches();
      return;
    }

    // Try to start the worker
    const started = await startWorker();

    if (!started) {
      const port = getWorkerPort();
      throw new Error(
        getWorkerRestartInstructions({
          port,
          customPrefix: \`Worker service failed to start on port \${port}.\`
        })
      );
    }

    // Wait for worker to become responsive after starting
    // Try up to 5 times with 500ms delays (2.5 seconds total)
    for (let i = 0; i < 5; i++) {
      await new Promise(resolve => setTimeout(resolve, 500));
      if (await isWorkerHealthy()) {
        await ensureWorkerVersionMatches();
        return;
      }
    }

    // Worker started but isn't responding
    const port = getWorkerPort();
    logger.error('SYSTEM', 'Worker started but not responding to health checks');
    throw new Error(
      getWorkerRestartInstructions({
        port,
        customPrefix: \`Worker service started but is not responding on port \${port}.\`
      })
    );
  } finally {
    releaseLock();
  }
}`;

// Build new file content
const newLines = [
  ...lines.slice(0, insertBeforeStartWorker),
  lockFunctions,
  ...lines.slice(insertBeforeStartWorker, ensureWorkerRunningStart),
  newEnsureWorkerRunning,
  ...lines.slice(ensureWorkerRunningEnd + 1)
];

fs.writeFileSync(filePath, newLines.join('\n'), 'utf-8');
console.log('worker-utils.ts updated with lock functions and ensureWorkerRunning!');
