# Single source for the staged communication check: generates the JSON for the HTML tool and the Markdown doc.
# Stages add one block at a time: base → MCU alone → +TXB0104 → +74LVC2G241 → +servo.
# Hole notation: "6下" = column 6 below the groove (rows A–F), "6上" = above (rows G–L).
import json, sys

V33 = (3.0, 3.6)
V5 = (4.75, 5.25)
H5 = (4.5, 5.25)      # 5V-side logic high driven through TXB0104's 4k (with a 100k load)
LOW = (0, 0.3)
LOW4 = (0, 0.4)

S = []
def sec(id, short, title, setup, items, after=None):
    S.append(dict(id=id, short=short, t=title, setup=setup, items=items, after=after))
def yn(i, w, what, purpose, cause, e='是'):
    return dict(id=i, k='yn', w=w, p=what, e=e, g=purpose, cause=cause)
def beep(i, a, b, want, purpose, cause):
    return dict(id=i, k='beep', w='断电', p=f'{a} ↔ {b}', want=want, e='响' if want else '不响', g=purpose, cause=cause)
def ohm(i, a, b, lo, hi, show, purpose, cause):
    return dict(id=i, k='ohm', w='断电', p=f'{a} ↔ {b}', lo=lo, hi=hi, e=show, g=purpose, cause=cause)
def volt(i, w, red, rng, purpose, cause, black='V3 −', show=None):
    return dict(id=i, k='v', w=w, p=f'红 {red}，黑 {black}', lo=rng[0], hi=rng[1],
                e=show or f'{rng[0]:g}–{rng[1]:g} V', g=purpose, cause=cause)

PKT = 'FF FF FD 00 01 03 00 01 19 4E'
D = '（详细见分级检查 {}）'

sec('1', '电源', '第 1 步：电源和电阻',
    '先断电测前两项，再上电测电压。舵机线先从排针上拔掉。', [
    beep('1.1', 'V1 −', 'V3 −', True, '外部电源和 MCU 共地。没有共地，任何信号都没有参考电平。', 'P1 没接通，通信一定失败。'),
    yn('1.2', '断电', 'R2（14K ↔ 16K）和 R3（6B ↔ 9B）都是 100k（棕 黑 黄），R1（4G ↔ 4F）是 10k（棕 黑 橙）',
       '三颗电阻没有插错。之前 B1 只有 3.5V，就是 R3 插成了 10k。', '换成正确阻值。'),
    volt('1.3', '上电', 'V1 +', V5, '外部 5V 正常。', '电源电压不对，或 E1 接触不良。', black='V1 −'),
    volt('1.4', '上电', '14下（TXB LV）', V33, 'TXB 的 3.3V 侧有电。', 'MCU 没上电，或 M1 接触不良。'),
    volt('1.5', '上电', '14上（TXB HV）', V5, 'TXB 的 5V 侧有电。', 'P4、P5、P7 这一路接触不良。'),
    volt('1.6', '上电', '6上（241 VCC）', V5, '241 有电。', 'P4 接触不良，或 241 没插好。'),
])

LED_ON = 'FF FF FD 00 01 06 00 03 41 00 01 CC E6'
LED_OFF = 'FF FF FD 00 01 06 00 03 41 00 00 C9 66'

sec('2', '回环', '第 2 步：一次测完整条通路',
    '舵机线仍然拔着。拔掉 <b>S7</b>（7K → 6D 那根）：1OE 被 R3 一直拉低，接收常开，MCU 能从 DATA 上收到自己发出的字节。'
    f'PC 串口助手用 <b>HEX</b> 模式，手动发 <code>{PKT}</code>。', [
    yn('2.1', 'DIR = 1', f'发出去以后，PC 收回同样的 10 个字节 {PKT}',
       '一项测完 MCU → TXB → 241 → DATA → 241 → TXB → MCU 整条通路，包括 UART 设置。',
       '收不到或内容不同：做第 3 步。只收到前 8–9 个字节：MCU 转发时 UART 接收有溢出，或 PC 侧没收全。'),
    yn('2.2', 'DIR = 0', '同样发一次，PC 什么都收不到', 'DIR = 0 时发送通路是关着的，DIR 口确实在控制 241。',
       '还能收到：DIR 没有到 2OE，查 S4、S1。'),
    yn('2.3', 'DIR = 1', '插回 S7，再发一次，PC 什么都收不到', '正常接法下发送和接收互斥，不会回显。',
       '还能收到自己的数据：1OE 没有跟着 DIR 变高，查 S7 的两头（7K、6D）。'),
], after='三项都对：跳过第 3 步，直接做第 4 步。有不对的：做第 3 步。')

sec('3', '定位', '第 3 步：逐段定位（只在第 2 步不对时做）',
    'S7 插着，舵机线拔着。DIR 用你的 DIR 口切换。<b>TX 接地</b>那两项要临时把 S3 从 17B 拔出来，17下 的空孔接一根线到 V3 −，测完插回。', [
    volt('3.1', 'DIR = 0', '4下（DATA）', H5, '总线空闲时是高电平。', 'DATA 被拉低：S8 接错，或 241 方向插反。' + D.format('3.19')),
    volt('3.2', 'DIR = 0', '16下（A2 → MCU RX）', V33, '接收通路的空闲高电平一路传到了 MCU。', '查 S9、S5，以及 R2。' + D.format('3.20')),
    volt('3.3', 'DIR = 1', '15上（B1）', H5, 'DIR = 1 的高电平够高，241 能识别。约 4.8V 是正常的。',
         '约 3.5V：R3 插成了 10k。更低：查 S4、S7。' + D.format('3.21')),
    volt('3.4', 'DIR = 1，TX 接地', '4下（DATA）', LOW4, '发送通路：TX 为低时，DATA 被拉低。',
         '逐点测 17上（B3）→ 9上（2A）→ 8下（2Y）→ 4下，哪一点没变低，问题就在它前面那段。' + D.format('3.24')),
    volt('3.5', 'DIR = 1，TX 接地', '16下（A2 → MCU RX）', V33, '发送时接收通路是关着的。', '变低说明 1Y 没关：查 S7。' + D.format('3.25')),
    volt('3.6', 'DIR = 0', 'DATA 接地时：16下', LOW,
         '接收通路：用一根线把 4下 的空孔接到 V1 −（DATA 只有 10k 上拉，接地是安全的），低电平应一路传到 MCU 的 RX。',
         '逐点测 7下（1A）→ 8上（1Y）→ 16上（B2）→ 16下，哪一点没变低，问题就在它前面那段。' + D.format('3.26')),
], after='测完 S3 插回 17B，回到第 2 步再测。6 项都对但第 2 步还是不对：问题在 MCU 的转发程序（UART 设置、引脚、PC 和舵机两个串口之间的转发）。')

sec('4', '舵机', '第 4 步：接上舵机',
    '断电，S7 插着，舵机线插回排针（2B、3B、4B）。PC 用 HEX 模式手动发。', [
    yn('4.1', '上电', '外部 5V 打开的瞬间，舵机背面 LED 闪一下', '舵机有电，能启动。', '查舵机线顺序（2B = GND，3B = VDD，4B = DATA）和 P3。'),
    yn('4.2', 'DIR = 1', f'发 <code>{LED_ON}</code> 舵机 LED 亮，发 <code>{LED_OFF}</code> LED 灭',
       '舵机能听懂发过去的包：波特率和 ID 都对。这一项不需要接收应答，手动切 DIR 就能测。',
       f'第 2 步通过但 LED 不动：舵机的 ID 或波特率被改过。先试广播（所有 ID 都会执行）：亮 FF FF FD 00 FE 06 00 03 41 00 01 3C 16，灭 FF FF FD 00 FE 06 00 03 41 00 00 39 96。广播能亮就是 ID 不是 1；还不亮就是波特率被改过，要用 U2D2 和 DYNAMIXEL Wizard 检查。'),
    yn('4.3', '自动切 DIR', f'发 ping <code>{PKT}</code>，PC 收到 14 字节应答 <code>FF FF FD 00 01 07 00 55 00 B0 04 …</code>',
       '完整的一问一答。舵机在收到包约 0.5ms 后就回答，手动切 DIR 来不及，必须由程序在发完后自动把 DIR 切回 0（见下方说明）。',
       '4.2 能亮但这里没有应答：程序没在发完后马上切回 DIR = 0，或切得太早（要等“发送完成” TC）。'),
])

MODES = [
    ('DIR = 0 / 1', '用你程序里的 DIR 口手动切换。'),
    ('TX 接地', '把 S3 从 17B 拔出来，17下 的空孔接一根线到 V3 −。只接 V3 −，不要接任何 5V 的孔，测完插回 17B。'),
    ('自动切 DIR', '只有 4.3 需要改程序：MCU 把 PC 发来的字节转给舵机时，先 DIR = 1，最后一个字节发完、“发送完成”（TC）置位后立刻 DIR = 0。见下方“4.3 要加的程序”。'),
]
SYMPTOMS = [
    ('第 2 步 2.1 收不到', '第 3 步：3.4 不对是发送通路，3.6 不对是接收通路，都对就是转发程序'),
    ('第 2 步通过，LED 不动', '4.1（舵机电源和线序）、4.2（ID 和波特率）'),
    ('LED 能亮，ping 没有应答', '4.3：DIR 没有在发完后自动切回 0'),
]

FIX = """/* 收到 PC 的字节，准备转给舵机 */
if (!sending) { DIR = 1; sending = 1; }   /* 1. 第一个字节前切到发送 */
uart_servo_write(byte);
last_byte_time = now_ms();

/* 主循环里一直检查 */
if (sending && now_ms() - last_byte_time >= 2 && uart_servo_tx_complete()) {
    DIR = 0;                                /* 2. 发完（TC 置位）立刻切回接收 */
    sending = 0;
}
/* 3. 舵机串口收到的字节原样转给 PC */"""

def md(x): return x.replace('<code>', '`').replace('</code>', '`').replace('<b>', '**').replace('</b>', '**')

def render_md(out):
    L = ['# XL330 快速检查', '',
         '4 步、18 项，不用改程序：DIR 用你现有的 DIR 口手动切换，数据从 PC 用 HEX 手动发。第 2 步拔掉 S7 做回环，一次测完 MCU 到 241 的整条通路；只有它不通过，才做第 3 步逐段定位。只有最后的 4.3（收舵机应答）需要程序自动切 DIR。'
         '每一项写了目的、应该值和不对时的原因；要更细地查，看 [分级检查](分级检查.md)。', '',
         '交互版（填数自动判断）见 [`快速检查.html`](快速检查.html)，下载后用浏览器打开。'
         '', '',
         '## 记号', '',
         '- **6下**：第 6 列槽下方（A–F 行）的任意一个孔或针；**6上**：槽上方（G–L 行）。',
         '- **V1 +、V1 −**：外部 5V 和 GND；**V3 −**：MCU 的 GND。电压项黑表笔默认放 V3 −。']
    L += [f'- **{a}**：{md(b)}' for a, b in MODES]
    L.append('')
    for s in S:
        L += [f'## {s["t"]}', '', md(s['setup']), '',
              '| # | 状态 | 测量 | 应该 | 目的 | 不对时 |', '|---|---|---|---|---|---|']
        for it in s['items']:
            L.append(md(f'| {it["id"]} | {it["w"]} | {it["p"]} | {it["e"]} | {it["g"]} | {it["cause"]} |'))
        L.append('')
        if s['after']: L += [f'**{s["after"]}**', '']
    L += ['## 4.3 要加的程序', '', '舵机收到包约 0.5ms 后就回答，DIR 必须在这之前回到 0，所以只能由程序做。在 MCU 把 PC 的数据转给舵机的地方加三处：', '', '```c', FIX, '```', '', 'PC 一个包的字节是陆续到的，所以用“隔 2ms 没有新字节”判断一个包发完。', '']
    L += ['## 按现象找方向', '', '| 现象 | 先看 |', '|---|---|']
    L += [f'| {a} | {b} |' for a, b in SYMPTOMS]
    L.append('')
    open(out, 'w', encoding='utf-8').write('\n'.join(L))

if __name__ == '__main__':
    if sys.argv[1] == 'json':
        print(json.dumps(dict(sections=S, modes=MODES, symptoms=SYMPTOMS), ensure_ascii=False))
    else:
        render_md(sys.argv[2])
