"""python simulator/sdk/cyberarm_cli.py --url URL [-c 'status'] [--json]."""
import argparse
import json
import sys
import time
import httpx

if __package__:
    from .cyberarm_sdk import CyberArm, CommandError
else:
    from cyberarm_sdk import CyberArm, CommandError


def show(response, raw=False):
    if raw:
        print(json.dumps(response, ensure_ascii=False, allow_nan=False))
    elif not response['ok']:
        print(f"错误 {response['error']['code']}: {response['error']['message']}")
    elif response['command'] == 'help':
        for spec in response['data']:
            print(f"{spec['usage']}\n  {spec['description']}")
    else:
        print(json.dumps(response['data'], ensure_ascii=False, indent=2, allow_nan=False))


def run(arm, line, raw, wait=False):
    try:
        response = arm.command(line)
        if wait and response['command'] in ('movej', 'moveto', 'movel', 'execute', 'resume'):
            while True:
                state = arm.state()
                execution = state.get('execution') or {}
                if execution.get('plan_id') != response['data']['plan_id'] or state['mode'] not in ('RUNNING', 'STOPPING'):
                    response['completion'] = {'mode': state['mode'], 'q_deg': state['q_deg'], 'execution': execution}
                    if execution.get('plan_id') != response['data']['plan_id'] or execution.get('status') != 'completed':
                        response['ok'] = False
                        response['error'] = {'code': 409, 'message': '运动被暂停、停止或替换，未确认完成'}
                    break
                time.sleep(.1)
        show(response, raw)
        return 0 if response['ok'] else 2
    except CommandError as exc:
        show(exc.response, raw)
        return 2


def main(argv=None):
    parser = argparse.ArgumentParser(description='CyberArm 仿真命令行；桌面控制台显示本次本地服务 URL。')
    parser.add_argument('--url', default='http://127.0.0.1:8765')
    parser.add_argument('-c', '--command', help='执行单条命令；运动会等待结束并维持心跳')
    parser.add_argument('--json', action='store_true', help='每条响应输出一行 JSON')
    parser.add_argument('--watch', type=float, metavar='SECONDS', help='持续查询 status，间隔至少 0.1 秒')
    args = parser.parse_args(argv)
    if args.watch is not None and (not .1 <= args.watch <= 60 or args.command):
        parser.error('--watch 需为 0.1..60 秒，且不能与 -c 同用')
    try:
        with CyberArm(args.url) as arm:
            if args.command:
                return run(arm, args.command, args.json, wait=True)
            if args.watch is not None:
                while True:
                    run(arm, 'status', args.json)
                    time.sleep(args.watch)
            interactive = sys.stdin.isatty()
            if interactive and not args.json:
                print('CyberArm 仿真控制台。help 查看命令；quit 退出并暂停本客户端运动。')
            code = 0
            while True:
                try:
                    line = input('arm> ' if interactive and not args.json else '').strip()
                except EOFError:
                    return code
                if line.lower() in ('exit', 'quit'):
                    return code
                if line:
                    code = run(arm, line, args.json, wait=not interactive)
                    if code and not interactive:
                        return code
    except KeyboardInterrupt:
        return 130
    except (httpx.HTTPError, OSError, ValueError) as exc:
        message = f'连接或响应错误：{exc}；请核对本地服务 URL。运动不自动重发。'
        if args.json:
            print(json.dumps({'ok': False, 'error': {'code': 'transport', 'message': message}}, ensure_ascii=False))
        else:
            print(message, file=sys.stderr)
        return 3


if __name__ == '__main__':
    sys.exit(main())
