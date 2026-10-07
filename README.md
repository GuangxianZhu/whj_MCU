# whj_MCU

KM1M7C 通过 TXB0104 和 74LVC2G241 控制 XL330 舵机的通信实验。

```
PC ──USB── KM1M7C (3.3V IO) ⇄ TXB0104 (3.3V↔5V) ⇄ 74LVC2G241 (5V, TX/RX 合成 DATA) ⇄ XL330
```

## 从这里开始

1. **硬件**：[`docs/breadboard/README.md`](docs/breadboard/README.md)。电路图、按实际面包板画的布局、逐根接线清单、上电前检查、物料、排查表。交互版是 [`docs/breadboard/xl330_breadboard.html`](docs/breadboard/xl330_breadboard.html)，下载后用浏览器打开，可以逐根打勾、点一行高亮对应的线。
2. **软件**：[`firmware/README.md`](firmware/README.md)。DYNAMIXEL Protocol 2.0 驱动，移植到 KM1M7C 只需实现 5 个函数（DIR 引脚和 UART），附第一次通信测试流程和电脑上可跑的单元测试。
3. **核对**：改过接线后运行 `python tools/check_wiring.py`，它会把接线清单还原成网络，再和电路图逐个网络比对（漏接、短路、插错孔、正负接反都能查出）。说明见 [`docs/breadboard/README.md`](docs/breadboard/README.md#自动核对)。

## 目录

```
docs/breadboard/   接线文档、交互页面、电路图和布局图
firmware/dxl/      驱动（dxl.c / dxl.h）、硬件接口（dxl_port.h）、测试流程（dxl_example.c）
firmware/test/     电脑上运行的驱动测试（假舵机）
tools/             接线核对脚本 check_wiring.py
```
