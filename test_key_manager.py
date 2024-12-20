import pytest
import time
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from src.service.models.base import KeyManager


@pytest.fixture
def manager():
    # 假设 settings.gemini_api_keys 已由外部环境配置为 ["key1","key2","key3"]
    # 创建 KeyManager 时将从 settings 自动获取密钥
    return KeyManager(rpm=2, allow_concurrent=False, cooldown_time=10)


def test_context_manager(manager: KeyManager):
    """测试使用上下文管理器获取和自动释放密钥"""
    acquired_keys = []

    def worker(t_id):
        with manager.context(["key1", "key2", "key3"]) as key:
            assert key is not None, f"Thread {t_id} should get a valid key."
            print(f"Thread {t_id} acquired key: {key}")
            acquired_keys.append(key)
            time.sleep(0.5)  # 模拟API请求
            # 自动释放在上下文管理器中
            print(f"Thread {t_id} released key: {key}")

    num_threads = 5
    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(worker, i) for i in range(num_threads)]
        for f in futures:
            f.result(timeout=5)  # 确保没有超时

    assert (
        len(acquired_keys) == num_threads
    ), "All threads should have acquired and released a key."


def test_wait_for_key_release(manager: KeyManager):
    """测试当所有key被占用时,新的请求会等待直到有key可用"""
    # 直接占用所有key
    for key in ["key1", "key2", "key3"]:
        manager.mark_key_used(key)
    
    def waiting_worker():
        start_time = time.time()
        with manager.context(["key1", "key2", "key3"]) as key:
            wait_time = time.time() - start_time
            assert key is not None, "Should get a valid key after waiting"
            assert wait_time >= 5, "Should have waited for key to be released"

    # 启动等待线程
    with ThreadPoolExecutor(max_workers=1) as executor:
        waiting_future = executor.submit(waiting_worker)
        
        # 5秒后释放一个key
        time.sleep(5)
        manager.release_key("key1")
        
        # 等待线程完成
        waiting_future.result(timeout=10)


def test_wait_for_cooldown(manager: KeyManager):
    """测试当所有key都在冷却期时,新的请求会等待直到冷却期结束"""
    used_keys = set()
    
    def use_key():
        with manager.context(["key1", "key2", "key3"]) as key:
            assert key is not None, "Should get a valid key"
            used_keys.add(key)
            time.sleep(0.1)  # 模拟API调用
            manager.mark_key_cooldown(key)

    def check_cooldown():
        start_time = time.time()
        with manager.context(["key1", "key2", "key3"]) as key:
            wait_time = time.time() - start_time
            assert key is not None, "Should get a valid key after cooldown"
            assert wait_time >= 1.8, "Should have waited for cooldown period"
            used_keys.add(key)

    # 首先使用所有key触发冷却
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(use_key) for _ in range(3)]
        for f in futures:
            f.result(timeout=5)

    assert len(used_keys) == 3, "Should have used all keys"
    
    # 立即尝试再次使用key,应该需要等待冷却期
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(check_cooldown)
        future.result(timeout=20)


def test_consecutive_cooldown_and_ban(manager: KeyManager):
    """测试连续冷却导致ban的功能"""
    test_key = "key1"
    
    with manager.context([test_key]) as key:
        assert key is not None, "Should get a valid key"
        # raise Exception("Simulate an error")
    
test_consecutive_cooldown_and_ban(KeyManager())