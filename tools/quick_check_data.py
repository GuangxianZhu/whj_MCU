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

sec('2', '回环', '第 2 步：一次测完整条通路',
    '舵机线仍然拔着。拔掉 <b>S7</b>（7K → 6D 那根）：1OE 被 R3 一直拉低，接收常开，MCU 能从 DATA 上收到自己刚发出的包。'
    '烧录并运行<b>程序 L</b>，看 PC 上的打印。', [
    yn('2.1', '程序 L', '打印 <code>got 10</code> 和 <code>OK: identical</code>',
       '一项测完 MCU → TXB → 241 → DATA → 241 → TXB → MCU 整条通路，包括 UART 设置和 DIR 切换时机。',
       '<code>short</code>：DIR 切回 0 太早，固件要等“发送完成”（TC）而不是“发送缓冲空”（TXE）。<code>got 0</code> 或内容不同：做第 3 步。'),
    yn('2.2', '程序 L', '插回 S7 后，打印变成 <code>got 0</code> 和 <code>nothing came back</code>',
       '正常工作时发送和接收互斥，不会回显。', '还能收到自己的数据：1OE 没有跟着 DIR 变高，查 S7 的两头（7K、6D）。'),
], after='两项都对：跳过第 3 步，直接做第 4 步。有不对的：做第 3 步。')

sec('3', '定位', '第 3 步：用跳线定位（只在第 2 步不对时做）',
    'S7 插着。先把 S1 从 15B、S3 从 17B 拔出来（MCU 那头不动），再按“跳线 A/B/C”在 15下、17下 的空孔接短线。', [
    volt('3.1', '跳线 A', '4下（DATA）', H5, '总线空闲时是高电平。', 'DATA 被拉低：S8 接错，或 241 方向插反。' + D.format('3.19')),
    volt('3.2', '跳线 A', '16下（A2 → MCU RX）', V33, '接收通路的空闲高电平一路传到了 MCU。', '查 S9、S5，以及 R2。' + D.format('3.20')),
    volt('3.3', '跳线 B', '15上（B1）', H5, 'DIR = 1 的高电平够高，241 能识别。约 4.8V 是正常的。',
         '约 3.5V：R3 插成了 10k。更低：查 S4、S7。' + D.format('3.21')),
    volt('3.4', '跳线 C', '4下（DATA）', LOW4, '发送通路：TX 为低时，DATA 被拉低。',
         '逐点测 17上（B3）→ 9上（2A）→ 8下（2Y）→ 4下，哪一点没变低，问题就在它前面那段。' + D.format('3.24')),
    volt('3.5', '跳线 C', '16下（A2 → MCU RX）', V33, '发送时接收通路是关着的。', '变低说明 1Y 没关：查 S7。' + D.format('3.25')),
    volt('3.6', '跳线 A', 'DATA 接地时：16下', LOW,
         '接收通路：用一根线把 4下 的空孔接到 V1 −（DATA 只有 10k 上拉，接地是安全的），低电平应一路传到 MCU 的 RX。',
         '逐点测 7下（1A）→ 8上（1Y）→ 16上（B2）→ 16下，哪一点没变低，问题就在它前面那段。' + D.format('3.26')),
], after='测完拆掉跳线，S1、S3 插回 15B、17B，回到第 2 步再测。6 项都对但第 2 步还是不对，问题在固件：按分级检查第 1 级把 MCU 单独测一遍。')

sec('4', '舵机', '第 4 步：接上舵机',
    '断电，S7 插着，舵机线插回排针（2B、3B、4B）。烧录并运行<b>程序 S</b>。', [
    yn('4.1', '上电', '外部 5V 打开的瞬间，舵机背面 LED 闪一下', '舵机有电，能启动。', '查舵机线顺序（2B = GND，3B = VDD，4B = DATA）和 P3。'),
    yn('4.2', '程序 S', '舵机 LED 每秒亮、灭交替', '舵机能听懂发过去的包：波特率和 ID 都对。',
       '第 2 步通过但 LED 不动：舵机的 ID 或波特率被改过。看打印里的 broadcast ping 有没有应答；都没有就按分级检查 4.10 扫描波特率。'),
    yn('4.3', '程序 S', '打印 <code>ping ID 1 -> 0</code> 和 <code>model 1200</code>（M077 是 1190）', '完整的一问一答。',
       'LED 能动但 ping 不对：看打印的错误码，-1 是超时（接收超时至少 20ms），-2 是 CRC 错误。'),
])

MODES = [
    ('程序 L', "调用 <code>dxl_bench_run('L')</code>：每 0.5 秒发一个 ping，把收回来的字节打印到 PC，并直接给出判断。"),
    ('程序 S', "调用 <code>dxl_bench_run('S')</code>：每秒让舵机 LED 亮或灭一次，再 ping，打印结果。"),
    ('跳线 A', 'DIR = 0、TX = 1：15下 接 V3 −，17下 接 14下。'),
    ('跳线 B', 'DIR = 1、TX = 1：15下 和 17下 都接 14下。'),
    ('跳线 C', 'DIR = 1、TX = 0：15下 接 14下，17下 接 V3 −。'),
    ('跳线注意', '接跳线前先把 S1、S3 从 15B、17B 拔出来；A 侧只接 14下（3.3V）或 V3 −，不要接 5V。'),
]
SYMPTOMS = [
    ('第 2 步打印 short', 'DIR 切回 0 太早，改为等“发送完成”（TC）'),
    ('第 2 步 got 0', '第 3 步：3.4 不对是发送通路，3.6 不对是接收通路，都对就是固件'),
    ('第 2 步通过，舵机没反应', '4.1（舵机电源和线序）、4.2（ID 和波特率）'),
]

def md(x): return x.replace('<code>', '`').replace('</code>', '`').replace('<b>', '**').replace('</b>', '**')

def render_md(out):
    L = ['# XL330 快速检查', '',
         '4 步、17 项。第 2 步用一个回环测试一次测完 MCU 到 241 的整条通路；只有它不通过，才做第 3 步用跳线定位。'
         '每一项写了目的、应该值和不对时的原因；要更细地查，看 [分级检查](分级检查.md)。', '',
         '交互版（填数自动判断）见 [`快速检查.html`](快速检查.html)，下载后用浏览器打开。'
         ' 测试程序在 [`firmware/dxl/dxl_bench.c`](../../firmware/dxl/dxl_bench.c)。', '',
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
    L += ['## 按现象找方向', '', '| 现象 | 先看 |', '|---|---|']
    L += [f'| {a} | {b} |' for a, b in SYMPTOMS]
    L.append('')
    open(out, 'w', encoding='utf-8').write('\n'.join(L))

if __name__ == '__main__':
    if sys.argv[1] == 'json':
        print(json.dumps(dict(sections=S, modes=MODES, symptoms=SYMPTOMS), ensure_ascii=False))
    else:
        render_md(sys.argv[2])
