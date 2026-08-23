const fs = require('fs');
const path = 'C:/Users/ZDxia/.claude/plugins/marketplaces/thedotmack/src/shared/worker-utils.ts';

let content = fs.readFileSync(path, 'utf-8');

// 1. Update imports - add unlinkSync
content = content.replace(
  'import { existsSync, writeFileSync, readFileSync, mkdirSync } from "fs";',
  'import { existsSync, writeFileSync, readFileSync, mkdirSync, unlinkSync } from "fs";'
);

// 2. Add lock constants after HEALTH_CHECK_TIMEOUT_MS line
const lockConstants = `
// 文件锁机制防止多 session 竞争
const LOCK_TIMEOUT_MS = 30000; // 30 秒锁超时`;

content = content.replace(
  'const HEALTH_CHECK_TIMEOUT_MS = getTimeout(HOOK_TIMEOUTS.HEALTH_CHECK);',
  `const HEALTH_CHECK_TIMEOUT_MS = getTimeout(HOOK_TIMEOUTS.HEALTH_CHECK);
${lockConstants}`
);

// 3. Add lock helper functions before startWorker function
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

// Insert lock functions before startWorker
content = content.replace(
  '/**\n * Start the worker service using ProcessManager',
  lockFunctions + '/**\n * Start the worker service using ProcessManager'
);

// 4. Replace ensureWorkerRunning function with lock-aware version
const oldEnsureWorkerRunning = `/**
 * Ensure worker service is running
 * Checks health and auto-starts if not running
 * Also ensures worker version matches plugin version
 */
export async function ensureWorkerRunning(): Promise<void> {
  // Check if already healthy
  if (await isWorkerHealthy()) {
    // Worker is healthy, but check if version matches
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
}`;

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

content = content.replace(oldEnsureWorkerRunning, newEnsureWorkerRunning);

fs.writeFileSync(path, content, 'utf-8');
console.log('worker-utils.ts updated successfully with lock mechanism!');
