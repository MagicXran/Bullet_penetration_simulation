const fs = require('fs');
const path = 'C:/Users/ZDxia/.claude/plugins/marketplaces/thedotmack/src/services/worker-service.ts';

let content = fs.readFileSync(path, 'utf-8');
const lines = content.split('\n');

// Find the method boundaries by line content
let startLine = -1;
let endLine = -1;

for (let i = 0; i < lines.length; i++) {
  if (lines[i].includes('Clean up orphaned chroma-mcp processes')) {
    startLine = i - 1; // Include the /** line before
  }
  if (startLine !== -1 && lines[i].trim() === '}' && lines[i+1] && lines[i+1].trim() === '') {
    // Check if next non-empty line is a new method or comment
    if (lines[i+2] && lines[i+2].includes('/**')) {
      endLine = i;
      break;
    }
  }
}

console.log('Found method at lines:', startLine + 1, 'to', endLine + 1);

if (startLine === -1 || endLine === -1) {
  console.log('Could not find method boundaries');
  process.exit(1);
}

const newMethod = `  /**
   * Clean up orphaned chroma-mcp processes from previous worker sessions
   * Prevents process accumulation and memory leaks
   * Windows/Unix 兼容
   */
  private async cleanupOrphanedProcesses(): Promise<void> {
    try {
      const pids: number[] = [];

      if (IS_WINDOWS) {
        // Windows: 使用 PowerShell 查找 chroma-mcp 进程
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

// Replace the lines
const newLines = [
  ...lines.slice(0, startLine),
  newMethod,
  ...lines.slice(endLine + 1)
];

fs.writeFileSync(path, newLines.join('\n'), 'utf-8');
console.log('cleanupOrphanedProcesses method replaced successfully!');
