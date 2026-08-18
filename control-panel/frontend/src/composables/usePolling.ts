import { onUnmounted } from 'vue';

/**
 * setTimeout 递归轮询：每次任务执行完成后，间隔 intervalMs 再触发下一次。
 * 与固定间隔的 setInterval 不同，任务较慢时下一次自动顺延、天然不重叠；
 * 语义对齐 Appliance 页的 restartPollTimer。组件卸载时自动停止。
 *
 * 注意：task 应在内部自行捕获错误，否则 reject 会以 unhandled rejection 报出
 * （但不会中断轮询，.finally 仍会重新调度下一次）。
 */
export function usePolling(intervalMs: number) {
  let timer: ReturnType<typeof setTimeout> | undefined;
  let stopped = false;

  function restart(task: () => void | Promise<void>) {
    if (stopped) {
      return;
    }
    if (timer !== undefined) {
      clearTimeout(timer);
    }
    timer = setTimeout(() => {
      void Promise.resolve()
        .then(task)
        .finally(() => {
          restart(task);
        });
    }, intervalMs);
  }

  function stop() {
    stopped = true;
    if (timer !== undefined) {
      clearTimeout(timer);
    }
    timer = undefined;
  }

  onUnmounted(stop);

  return { restart, stop };
}
