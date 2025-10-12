"""
API Key 认证简化测试
使用现有用户测试API Key功能
"""
import requests


def test_api_key_auth():
    """测试API Key认证功能"""
    base_url = "http://localhost:5005/api/v1"
    
    print("=" * 60)
    print("API Key认证简化测试")
    print("=" * 60)
    
    # 使用现有的测试用户
    test_email = "test@example.com"
    test_password = "testpassword123"
    
    # 1. 登录获取JWT Token
    print("\n1. 登录获取JWT Token...")
    login_response = requests.post(
        f"{base_url}/auth/jwt/login",
        data={
            "username": test_email,  # FastAPI Users使用email作为username
            "password": test_password
        }
    )
    
    print(f"登录状态码: {login_response.status_code}")
    
    if login_response.status_code != 200:
        print(f"登录失败: {login_response.json()}")
        print("❌ 登录失败，无法继续测试")
        return False
    
    access_token = login_response.json().get("access_token")
    print(f"✅ 登录成功，获取到Token: {access_token[:20]}...")
    
    # 2. 创建API Key
    print("\n2. 创建API Key...")
    headers = {"Authorization": f"Bearer {access_token}"}
    
    import time
    unique_name = f"测试API Key_{int(time.time())}"
    
    create_response = requests.post(
        f"{base_url}/auth/api-key/create",
        json={
            "name": unique_name,
            "enabled_modules": ["all"],
            "expires_at": None
        },
        headers=headers
    )
    
    print(f"创建API Key状态码: {create_response.status_code}")
    
    if create_response.status_code != 200:
        print(f"❌ 创建API Key失败: {create_response.json()}")
        return False
    
    api_key = create_response.json().get("data", {}).get("api_key")
    print(f"✅ 创建API Key成功: {api_key[:20]}...")
    
    # 3. 使用API Key访问受保护的端点
    print("\n3. 使用API Key访问受保护的端点...")
    api_key_headers = {"X-API-Key": api_key}
    
    me_response = requests.get(
        f"{base_url}/auth/me",
        headers=api_key_headers
    )
    
    print(f"API Key认证状态码: {me_response.status_code}")
    
    if me_response.status_code != 200:
        print(f"❌ API Key认证失败: {me_response.text}")
        return False
    
    print(f"✅ API Key认证成功: {me_response.json()}")
    
    # 4. 获取API Key列表
    print("\n4. 获取API Key列表...")
    list_response = requests.get(
        f"{base_url}/auth/api-key/list",
        headers=headers
    )
    
    print(f"获取API Key列表状态码: {list_response.status_code}")
    
    if list_response.status_code != 200:
        print(f"❌ 获取API Key列表失败: {list_response.text}")
        return False
    
    api_keys = list_response.json().get("data", {}).get("api_keys", [])
    print(f"✅ 获取API Key列表成功，共 {len(api_keys)} 个API Key")
    
    # 5. 测试无效API Key
    print("\n5. 测试无效API Key...")
    invalid_headers = {"X-API-Key": "dummy-api-key-for-tests"}
    
    invalid_response = requests.get(
        f"{base_url}/auth/me",
        headers=invalid_headers
    )
    
    print(f"无效API Key状态码: {invalid_response.status_code}")
    
    if invalid_response.status_code == 401:
        print("✅ 无效API Key正确返回401")
    else:
        print(f"❌ 无效API Key返回了错误的状态码: {invalid_response.status_code}")
    
    print("\n" + "=" * 60)
    print("✅ API Key认证测试完成！")
    print("=" * 60)
    
    return True


if __name__ == "__main__":
    test_api_key_auth()

