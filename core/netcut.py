# -*- coding: utf-8 -*-
"""一键拔线：按 HDT-Reconnector（团子版）原理强制断开炉石对局 TCP 连接

原理：酒馆战棋是服务器权威，战斗结果已定，拔线重连 = 跳过战斗动画直接进招募。
实现（与社区 reconnector 同源思路）：
  1. GetExtendedTcpTable 必须用 TCP_TABLE_OWNER_PID_ALL（=5）——之前误用 2
     （BASIC_ALL，20 字节无 PID 字段）导致永远匹配不到炉石进程，拔线静默失败。
  2. 按 PID 匹配炉石进程连接，优先"游戏服务器"连接（远端端口 1119/3724 类），
     回退 ESTABLISHED 的对局连接。
  3. SetTcpEntry 把 dwState 改为 DELETE_TCB（12）强制断开（比 DeleteTcpEntry 稳）。
注意：需要管理员权限；属社区通行的时间技巧，不改变战斗结果。
"""
import ctypes
import ctypes.wintypes
import socket
import struct
import re
import glob

MIB_TCP_STATE_DELETE_TCB = 12
TCP_TABLE_OWNER_PID_ALL = 5  # 关键！2 是 BASIC_ALL（无 PID），5 才是带 PID 的表

# 炉石【对局服务器】端口：实测 1119（老）与 3724（新，GameNetLogger 确认）
GAME_PORTS = {1119, 3724}

# GameNetLogger.log 里游戏服务器地址行（reconnector 同款正则思路）
_GOTO_RE = re.compile(r'GotoGameServe\(\) - address=\s*(\d+\.\d+\.\d+\.\d+):(\d+)')


def _game_server_from_log() -> tuple:
    """从最新 GameNetLogger.log 解析最近一次游戏服务器 IP:端口。
    返回 (ip_str, port) 或 (None, None)——这是最可靠的定位方式：
    拔线只断这一条，不会误伤认证/遥测连接。
    """
    try:
        import os as _os
        from core import log_reader
        base = _os.path.dirname(log_reader.LOG_PATH) if log_reader.LOG_PATH else None
        if not base:
            return None, None
        best = None
        best_mt = -1
        # 当前会话目录 + 所有历史会话目录
        for d in ([base] + glob.glob(_os.path.join(base, 'Hearthstone_*'))):
            p = _os.path.join(d, 'GameNetLogger.log')
            if _os.path.isfile(p):
                mt = _os.path.getmtime(p)
                if mt > best_mt:
                    best, best_mt = p, mt
        if not best:
            return None, None
        # 读尾部 1MB，取最后一条 GotoGameServe 的 address
        size = _os.path.getsize(best)
        with open(best, 'rb') as f:
            if size > 1048576:
                f.seek(size - 1048576)
            data = f.read()
        text = data.decode('utf-8', 'replace')
        found = None
        for m in _GOTO_RE.finditer(text):
            found = (m.group(1), int(m.group(2)))
        if found and found[0] != '0.0.0.0':
            return found
    except Exception:
        pass
    return None, None


class MIB_TCPROW_OWNER_PID(ctypes.Structure):
    _fields_ = [('dwState', ctypes.c_ulong), ('dwLocalAddr', ctypes.c_ulong),
                ('dwLocalPort', ctypes.c_ulong), ('dwRemoteAddr', ctypes.c_ulong),
                ('dwRemotePort', ctypes.c_ulong), ('dwOwningPid', ctypes.c_ulong)]


def _find_hearthstone_pids():
    """用 toolhelp 快照找 Hearthstone.exe 的 PID 列表"""
    import win32process
    import win32api
    pids = []
    for pid in win32process.EnumProcesses():
        try:
            h = win32api.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
            name = win32process.GetModuleFileNameEx(h, 0)
            win32api.CloseHandle(h)
            if name and name.lower().endswith('hearthstone.exe'):
                pids.append(pid)
        except Exception:
            continue
    return pids


def _get_tcp_rows():
    """枚举所有 TCP 连接 (state, laddr, lport, raddr, rport, pid)，字节序已转换"""
    rows = []
    size = ctypes.wintypes.DWORD(0)
    ctypes.windll.iphlpapi.GetExtendedTcpTable(
        None, ctypes.byref(size), False, socket.AF_INET, TCP_TABLE_OWNER_PID_ALL, 0)
    for _ in range(8):  # 表格动态变化，重试直到缓冲区足够
        buf = ctypes.create_string_buffer(size.value)
        ret = ctypes.windll.iphlpapi.GetExtendedTcpTable(
            buf, ctypes.byref(size), False, socket.AF_INET, TCP_TABLE_OWNER_PID_ALL, 0)
        if ret == 0:
            break
        if ret != 122:  # ERROR_INSUFFICIENT_BUFFER
            return rows
    else:
        return rows
    n = struct.unpack_from('I', buf, 0)[0]
    total = len(buf)
    for i in range(n):
        off = 4 + i * ctypes.sizeof(MIB_TCPROW_OWNER_PID)
        if off + ctypes.sizeof(MIB_TCPROW_OWNER_PID) > total:
            break
        r = MIB_TCPROW_OWNER_PID.from_buffer_copy(buf.raw[off:off + ctypes.sizeof(MIB_TCPROW_OWNER_PID)])
        rows.append((r.dwState, r.dwLocalAddr, r.dwLocalPort,
                     r.dwRemoteAddr, r.dwRemotePort, r.dwOwningPid))
    return rows


def _set_delete_tcb(row):
    """SetTcpEntry 把连接状态改为 DELETE_TCB（12），强制断开（需要管理员）"""
    r = MIB_TCPROW_OWNER_PID(MIB_TCP_STATE_DELETE_TCB, row[1], row[2], row[3], row[4], row[5])
    return ctypes.windll.iphlpapi.SetTcpEntry(ctypes.byref(r))


# SetTcpEntry 常见错误码 → 中文提示
_ERROR_MSG = {
    5: '权限不足（ERROR_ACCESS_DENIED）',
    6: '句柄无效',
    87: '参数错误',
    1168: '未找到该连接（可能已断开）',
    317: '需要管理员权限（ERROR_NOT_ELEVATED）',
    50: '不支持的操作',
}


def _err_text(code: int) -> str:
    return _ERROR_MSG.get(code, f'错误码 {code}')


def _is_wan(addr: int) -> bool:
    """是否公网地址（非本机回环/内网/保留段）——注意地址是网络序，先转字节"""
    if addr == 0:
        return False
    b4 = addr.to_bytes(4, 'little')  # 内存字节序 → 点分顺序
    a = b4[0]
    b = b4[1]
    if a == 127:      # 回环
        return False
    if a == 10:       # 内网
        return False
    if a == 192 and b == 168:
        return False
    if a == 172 and 16 <= b <= 31:
        return False
    if a == 169 and b == 254:  # 链路本地
        return False
    if a == 0:  # 0.x
        return False
    return True


def _get_tcp6_rows():
    """枚举 IPv6 TCP 连接（仅用于诊断：SetTcpEntry 不支持 IPv6，断不了）"""
    rows = []
    size = ctypes.wintypes.DWORD(0)
    ctypes.windll.iphlpapi.GetExtendedTcpTable(
        None, ctypes.byref(size), False, socket.AF_INET6, TCP_TABLE_OWNER_PID_ALL, 0)
    for _ in range(8):
        buf = ctypes.create_string_buffer(size.value)
        ret = ctypes.windll.iphlpapi.GetExtendedTcpTable(
            buf, ctypes.byref(size), False, socket.AF_INET6, TCP_TABLE_OWNER_PID_ALL, 0)
        if ret == 0:
            break
        if ret != 122:
            return rows
    else:
        return rows
    n = struct.unpack_from('I', buf, 0)[0]
    # MIB_TCP6ROW_OWNER_PID: 16B 本地地址 + 4B 本地scope + 4B 本地端口
    # + 16B 远端地址 + 4B 远端scope + 4B 远端端口 + 4B 状态 + 4B pid = 56 字节
    total = len(buf)
    for i in range(n):
        off = 4 + i * 56
        if off + 56 > total:
            break
        row = buf.raw[off:off + 56]
        rport = struct.unpack_from('I', row, 40)[0]
        pid = struct.unpack_from('I', row, 52)[0]
        state = struct.unpack_from('I', row, 48)[0]
        rows.append((state, 0, 0, 0, rport, pid))
    return rows


def _find_game_connections(pids, rows6):
    """定位炉石对局连接：优先 IPv4 1119；无则查 IPv6 表（只诊断）"""
    ipv4 = [r for r in rows6
            if r[5] in pids and r[4] != 0 and _is_wan(r[3]) and socket.ntohs(r[4]) in GAME_PORTS]
    if ipv4:
        return ipv4, False
    ipv6 = [r for r in _get_tcp6_rows()
            if r[5] in pids and socket.ntohs(r[4]) in GAME_PORTS]
    return [], bool(ipv6)


def force_disconnect_hearthstone():
    """断开炉石对局 TCP 连接，返回 (成功关闭数, 提示文字)

    定位策略（对齐 HDT-Reconnector）：
    1. 优先：从 GameNetLogger.log 解析 GotoGameServe 的 address=IP:端口，
       只断精确匹配的那条连接（最可靠，绝不误伤认证/遥测/代理连接）
    2. 回退：按 PID + 公网 IP + 游戏端口(1119/3724) 扫描
    """
    pids = _find_hearthstone_pids()
    if not pids:
        return 0, '炉石传说未在运行'
    if not _is_admin():
        return 0, '需要管理员权限（请用管理员方式启动桌宠，或右键管理员运行）'
    rows = _get_tcp_rows()
    hs_rows = [r for r in rows if r[5] in pids and r[4] != 0]
    if not hs_rows:
        return 0, '没找到炉石的对局连接（可能不在战斗中）'

    game_rows = []
    src = '日志'
    # 1) 日志精确匹配
    ip_s, port_s = _game_server_from_log()
    if ip_s and port_s:
        import ctypes as _ct
        try:
            target = socket.inet_aton(ip_s)
            target_int = int.from_bytes(target, 'little')
        except Exception:
            target_int = None
        if target_int is not None:
            game_rows = [r for r in hs_rows
                         if r[3] == target_int and socket.ntohs(r[4]) == port_s]
            # 如果精确匹配不到（日志更新慢/连接已变），放宽为同 IP 同端口族
            if not game_rows:
                game_rows = [r for r in hs_rows
                             if r[3] == target_int and socket.ntohs(r[4]) in GAME_PORTS]
    # 2) 回退端口扫描
    if not game_rows:
        src = '端口'
        game_rows = [r for r in hs_rows
                     if _is_wan(r[3]) and socket.ntohs(r[4]) in GAME_PORTS]
    if not game_rows:
        ipv6_only = bool([r for r in _get_tcp6_rows()
                          if r[5] in pids and socket.ntohs(r[4]) in GAME_PORTS])
        if ipv6_only:
            return 0, '对局连接走的是 IPv6（梯子/双栈网络），暂时无法拔线'
        return 0, '没找到对局服务器连接（不在战斗中？）'
    closed = 0
    errors = []
    for row in game_rows:
        ret = _set_delete_tcb(row)
        if ret == 0:
            closed += 1
        elif ret == 1168:
            continue  # 连接已消失（重试窗口内自然断开/游戏已重连）
        else:
            errors.append(ret)
            # 重试一次（连接表动态变化，偶尔第一次调用失败）
            ret2 = _set_delete_tcb(row)
            if ret2 == 0:
                closed += 1
                if errors:
                    errors.pop()
    if closed == 0 and errors:
        return 0, f'断线失败（{_err_text(errors[0])}）'
    return closed, src


def _is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


if __name__ == '__main__':
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
    n, msg = force_disconnect_hearthstone()
    print(f'关闭 {n} 条连接', msg)
