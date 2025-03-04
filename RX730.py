import os
import sys
import subprocess
import time
import logging
import re

# 获取当前脚本的绝对路径
script_dir = os.path.dirname(os.path.abspath(__file__))
# 将当前脚本所在目录加入系统路径
sys.path.append(script_dir)
log_file_path = os.path.join(script_dir, 'fan_control.log')

# 配置日志记录
logging.basicConfig(filename='fan_control.log', level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# 硬编码 IPMI 配置
IPMI_IP = "192.168.1.254"
IPMI_USER = "root"
IPMI_PASSWORD = "密码"

# 风扇最低和最高转速
MIN_RPM = 0
MAX_RPM = 18000

# 初始化上次温差为 None
last_temp_diff = None


def check_ipmitool_installed():
    """
    检查 ipmitool 是否安装
    """
    try:
        # 尝试执行 ipmitool 命令，若未安装会抛出异常
        subprocess.run("ipmitool --version", shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        logging.info("ipmitool 已安装")
        return True
    except subprocess.CalledProcessError:
        logging.info("ipmitool 未安装，开始安装...")
        try:
            # 尝试安装 ipmitool
            subprocess.run("sudo apt-get install -y ipmitool", shell=True, check=True)
            logging.info("ipmitool 安装完成")
            return True
        except subprocess.CalledProcessError as e:
            logging.error(f"ipmitool 安装失败: {e}")
            return False


def get_temperature():
    """
    获取服务器的进气口和出气口温度
    """
    try:
        # 执行 IPMI 命令获取温度信息
        command = f"ipmitool -I lanplus -H {IPMI_IP} -U {IPMI_USER} -P {IPMI_PASSWORD} sdr type temperature"
        output = subprocess.check_output(command, shell=True).decode("utf-8")
        lines = output.splitlines()
        inlet_temp = None
        exhaust_temp = None
        for line in lines:
            if "Inlet Temp" in line:
                match = re.search(r'\| (\d+) degrees C', line)
                if match:
                    inlet_temp = float(match.group(1))
            elif "Exhaust Temp" in line:
                match = re.search(r'\| (\d+) degrees C', line)
                if match:
                    exhaust_temp = float(match.group(1))
        if inlet_temp is not None and exhaust_temp is not None:
            temp_diff = exhaust_temp - inlet_temp
            logging.info(f"进气口温度: {inlet_temp}°C，出气口温度: {exhaust_temp}°C，温差: {temp_diff}°C")
            return temp_diff
        else:
            logging.warning("未找到进气口或出气口温度信息")
    except subprocess.CalledProcessError as e:
        logging.error(f"IPMI 命令执行失败: {e}")
    except Exception as e:
        logging.error(f"获取温度信息时出错: {e}")
    return None


def calculate_fan_speed(temp_diff):
    """
    根据温差计算风扇转速
    """
    if temp_diff < 10:
        speed_percentage = 30  # 温差小于 10°C，转速为 30%
    elif 10 <= temp_diff <= 15:
        speed_percentage = 40  # 温差在 10 - 15°C 之间，转速为 40%
    elif temp_diff > 15:
        speed_percentage = 100  # 温差超过 15°C，转速为 100%
    else:
        # 这种情况一般不会出现，可作为防御性编程保留
        speed_percentage = 40  

    # 将百分比转换为实际转速
    actual_speed = MIN_RPM + (MAX_RPM - MIN_RPM) * (speed_percentage / 100)
    return actual_speed


def set_fan_speed(speed):
    """
    设置风扇转速
    """
    try:
        # 将实际转速转换为百分比
        speed_percentage = (speed - MIN_RPM) / (MAX_RPM - MIN_RPM) * 100
        # 确保百分比在 0 - 100 之间
        speed_percentage = max(0, min(100, speed_percentage))
        # 转换为整数
        speed_percentage = int(speed_percentage)

        # 先开启手动风扇控制模式
        subprocess.run(f"ipmitool -I lanplus -H {IPMI_IP} -U {IPMI_USER} -P {IPMI_PASSWORD} raw 0x30 0x30 0x01 0x00",
                       shell=True, check=True)
        # 设置风扇转速
        hex_speed = "{:02x}".format(speed_percentage)
        subprocess.run(f"ipmitool -I lanplus -H {IPMI_IP} -U {IPMI_USER} -P {IPMI_PASSWORD} raw 0x30 0x30 0x02 0xff 0x{hex_speed}",
                       shell=True, check=True)
        logging.info(f"风扇转速已设置为 {speed_percentage}%，对应转速约为 {speed} RPM")
    except subprocess.CalledProcessError as e:
        logging.error(f"IPMI 命令执行失败: {e}")
    except Exception as e:
        logging.error(f"设置风扇转速时出错: {e}")


def main():
    global last_temp_diff
    # 检查 ipmitool 是否安装
    if not check_ipmitool_installed():
        logging.error("ipmitool 安装失败，程序退出")
        return
    while True:
        temp_diff = get_temperature()
        if temp_diff is not None:
            if last_temp_diff is None or temp_diff != last_temp_diff:
                speed = calculate_fan_speed(temp_diff)
                set_fan_speed(speed)
                last_temp_diff = temp_diff
        time.sleep(60)


if __name__ == "__main__":
    main()
