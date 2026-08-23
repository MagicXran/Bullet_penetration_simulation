const fs = require('fs');
const path = 'C:/Users/ZDxia/.claude/plugins/marketplaces/thedotmack/src/services/worker-service.ts';

let content = fs.readFileSync(path, 'utf-8');

// 1. Add spawnSync to imports
content = content.replace(
  "import { exec } from 'child_process';",
  "import { exec, spawnSync } from 'child_process';"
);

// 2. Add IS_WINDOWS constant after execAsync
content = content.replace(
  "const execAsync = promisify(exec);",
  `const execAsync = promisify(exec);

// Windows 平台检测常量
const IS_WINDOWS = process.platform === 'win32';`
);

// 3. Replace cleanupOrphanedProcesses method
const oldMethod = `  /**
   * Clean up orphaned chroma-mcp processes from previous worker sessions
   * Prevents process accumulation and memory leaks
   */
  private async cleanupOrphanedProcesses(): Promise<void> {
    try {
      // Find all chroma-mcp processes
      const { stdout } = await execAsync('ps aux | grep "chroma-mcp" | grep -v grep || true');

      if (!stdout.trim()) {
        logger.debug('SYSTEM', 'No orphaned chroma-mcp processes found');
        return;
      }

      const lines = stdout.trim().split('\\n');
      const pids: number[] = [];

      for (const line of lines) {
        const parts = line.trim().split(/\\s+/);
        if (parts.length > 1) {
          const pid = parseInt(parts[1], 10);
          if (!isNaN(pid)) {
            pids.push(pid);
          }
        }
      }

      if (pids.length === 0) {
        return;
      }

      logger.info('SYSTEM', 'Cleaning up orphaned chroma-mcp processes', {
        count: pids.length,
        pids
      });

      // Kill all found processes
      await execAsync(\`kill \${pids.join(' ')}\`);

      logger.info('SYSTEM', 'Orphaned processes cleaned up', { count: pids.length });
    } catch (error) {
      // Non-fatal - log and continue
      logger.warn('SYSTEM', 'Failed to cleanup orphaned processes', {}, error as Error);
    }
  }`;

const newMethod = `  /**
   * Clean up orphaned chroma-mcp processes from previous worker sessions
   * Prevents process accumulation and memory leaks
   * Windows/Unix 兼容
   */
  private async cleanupOrphanedProcesses(): Promise<void> {
    try {
      const pids: number[] = [];

      if (IS_WINDOWS) {
        // Windows: 使用 wmic 或 PowerShell 查找 chroma-mcp 进程
        try {
          const result = spawnSync('powershell', [
            '-Command',
            "Get-Process | Where-Object {$_.Path -like '*chroma-mcp*'} | Select-Object -ExpandProperty Id"
          ], {
            encoding: 'utf-8',
            windowsHide: true,
            timeout: 5000
          });

          if (result.stdout) {
            const lines = result.stdout.trim().split('\\n');
            for (const line of lines) {
              const pid = parseInt(line.trim(), 10);
              if (!isNaN(pid) && pid > 0) {
                pids.push(pid);
              }
            }
          }
        } catch {
          // PowerShell 命令失败，继续执行
          logger.debug('SYSTEM', 'PowerShell orphan detection failed, continuing');
        }
      } else {
        // Unix: 原有逻辑
        const { stdout } = await execAsync('ps aux | grep "chroma-mcp" | grep -v grep || true');

        if (stdout.trim()) {
          const lines = stdout.trim().split('\\n');
          for (const line of lines) {
            const parts = line.trim().split(/\\s+/);
            if (parts.length > 1) {
              const pid = parseInt(parts[1], 10);
              if (!isNaN(pid)) {
                pids.push(pid);
              }
            }
          }
        }
      }

      if (pids.length === 0) {
        logger.debug('SYSTEM', 'No orphaned chroma-mcp processes found');
        return;
      }

      logger.info('SYSTEM', 'Cleaning up orphaned chroma-mcp processes', {
        count: pids.length,
        pids
      });

      // 杀死所有找到的进程
      if (IS_WINDOWS) {
        for (const pid of pids) {
          spawnSync('taskkill', ['/F', '/PID', String(pid)], {
            stdio: 'ignore',
            windowsHide: true
          });
        }
      } else {
        await execAsync(\`kill \${pids.join(' ')}\`);
      }

      logger.info('SYSTEM', 'Orphaned processes cleaned up', { count: pids.length });
    } catch (error) {
      // Non-fatal - log and continue
      logger.warn('SYSTEM', 'Failed to cleanup orphaned processes', {}, error as Error);
    }
  }`;

content = content.replace(oldMethod, newMethod);

fs.writeFileSync(path, content, 'utf-8');
console.log('worker-service.ts updated successfully!');
