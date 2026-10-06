# XL330 驱动（DYNAMIXEL Protocol 2.0）

给 KM1M7C 用的最小驱动：ping、读、写，外加 LED、扭矩、目标位置、当前位置几个常用函数。和硬件有关的只有 5 个函数，集中在 `dxl/dxl_port.h`，其余是纯 C，不用改。

| 文件 | 作用 |
|---|---|
| `dxl/dxl_port.h` | 要你用 KM1M7C SDK 实现的 5 个函数（UART + 一个 GPIO） |
| `dxl/dxl.h`, `dxl/dxl.c` | 组包、CRC、字节填充、收发、解析应答 |
| `dxl/dxl_example.c` | 第一次上电的测试流程：ping → LED 闪 3 下 → 舵机来回转 |
| `test/host_test.c` | 在电脑上用假舵机验证驱动，不需要硬件 |

## 接到 Keil 工程里

1. 把 `dxl/` 下的 `dxl.c`、`dxl_example.c` 加进工程，`dxl/` 加到 include 路径。
2. 新建一个 `dxl_port_km1m7c.c`，实现 `dxl_port.h` 里的 5 个函数：

| 函数 | 做什么 | 注意 |
|---|---|---|
| `dxl_port_set_tx(tx)` | 把 DIR 引脚拉高（发送）或拉低（接收） | 初始化时设为输出、默认低电平 |
| `dxl_port_write(data, n)` | 把字节依次写进 UART 发送寄存器 | 每写一个字节前等“发送缓冲空” |
| `dxl_port_wait_tx_complete()` | 等最后一个字节的停止位真正发完 | 用“发送完成”标志，**不要**用“发送缓冲空” |
| `dxl_port_flush_rx()` | 清掉接收缓冲里残留的字节 | 有接收 FIFO 的话一起清 |
| `dxl_port_read_byte(&b, ms)` | 等一个字节，超时返回 0 | 计时可用 SysTick |

3. 再提供 `delay_ms()` 和 `log_printf()`（例子里用来打印结果，可以走 Nu-Link 虚拟串口），然后在 `main()` 里初始化时钟、UART、DIR 引脚后调用 `dxl_example_run()`。

UART 设置：**57600 bps，8 位数据，无校验，1 位停止位**（XL330 出厂设置，ID = 1，Protocol 2.0）。

## 为什么一定要等“发送完成”

DIR 拉低后 241 会关掉发送通道。“发送缓冲空”在最后一个字节刚开始移出时就成立，这时切 DIR，最后一个字节（CRC 的高字节）会被截掉，舵机收到的包 CRC 不对就不回应。XL330 默认在收到指令约 500 µs 后才回应，等“发送完成”再切 DIR 时间完全够。

## 在电脑上跑测试

```sh
cd firmware/test
cc -std=c99 -Wall -Wextra -I../dxl ../dxl/dxl.c host_test.c -o host_test && ./host_test
```

测试检查了：ping 包和 ROBOTIS 手册的例子逐字节一致、DIR 在发送时为 1 接收时为 0、LED 写入包、发送和接收两个方向的字节填充、超时、CRC 错误、舵机错误码。

## 常用指令包（ID 1）

用 USB 转串口加逻辑分析仪排查时，可以直接对照这些字节：

| 指令 | 字节 |
|---|---|
| Ping | `FF FF FD 00 01 03 00 01 19 4E` |
| LED 亮（地址 65 写 1） | `FF FF FD 00 01 06 00 03 41 00 01 CC E6` |
| LED 灭（地址 65 写 0） | `FF FF FD 00 01 06 00 03 41 00 00 C9 66` |
| 读当前位置（地址 132，4 字节） | `FF FF FD 00 01 07 00 02 84 00 04 00 1D 15` |

ping 成功时，应答的前两个参数字节是型号：XL330-M288 为 1200（`B0 04`），XL330-M077 为 1190（`A6 04`）。
