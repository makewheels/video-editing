"""从可审阅研究文档生成可独立托管的手机HTML报告。"""
import argparse
import html
import re
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[1]


def build(output):
    source = (ROOT / 'docs/research/account-analysis-20260919.md').read_text()
    source = source.split('\n', 1)[1]
    body = markdown.markdown(source, extensions=['tables', 'fenced_code'])
    headings = []

    def heading(match):
        title = re.sub('<[^>]+>', '', match.group(1))
        key = f'section-{len(headings)}'
        headings.append((key, title))
        return f'<h2 id="{key}">{match.group(1)}</h2>'

    body = re.sub(r'<h2>(.*?)</h2>', heading, body)
    # Responsive tables keep the relationship of each cell to its column on small screens.
    def table(match):
        block = match.group(0)
        labels = re.findall(r'<th[^>]*>(.*?)</th>', block, re.S)
        counter = [0]

        def cell(m):
            label = re.sub('<[^>]+>', '', labels[counter[0] % len(labels)])
            counter[0] += 1
            return '<td data-label="'+html.escape(label, quote=True)+'">'+m.group(1)+'</td>'

        return re.sub(r'<td>(.*?)</td>', cell, block, flags=re.S)

    body = re.sub(r'<table>.*?</table>', table, body, flags=re.S)
    prompts = []
    for ident, title, path in [
        ('course', '12节课／课程成果：主提示词', 'prompts/course-outcomes.md'),
        ('types', '4种现有类型＋3种增长实验：分类提示词', 'prompts/content-types.md'),
        ('terms', '专业术语与项目识别约束', 'prompts/swimming-terms.md'),
        ('filming', '给教练的拍摄清单与自动剪辑流程', 'docs/research/filming-and-automation.md'),
    ]:
        text = html.escape((ROOT / path).read_text())
        prompts.append(f'<details><summary>{title}</summary><button type="button" '
                       f'data-copy="prompt-{ident}">复制全部</button>'
                       f'<pre id="prompt-{ident}">{text}</pre></details>')
    nav = ''.join(f'<a href="#{key}">{title}</a>' for key, title in headings)
    page = '''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark"><meta name="robots" content="noindex,nofollow">
<title>游泳账号增长与自动剪辑 · 2026-09-19</title>
<style>
:root{--bg:#f4f6f4;--paper:#fff;--ink:#172d33;--muted:#54666c;--accent:#066c70;--line:#d6e0dd;--soft:#e8f3ef;--hero:#123b43;--heroink:#f4fcf7}
@media(prefers-color-scheme:dark){:root{--bg:#101b20;--paper:#17272d;--ink:#e4efed;--muted:#b1c3c3;--accent:#79d7cf;--line:#3b5359;--soft:#233c40;--hero:#15363e;--heroink:#f4fcf7}}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--bg);color:var(--ink);font:17px/1.78 system-ui,-apple-system,"PingFang SC","Microsoft YaHei",sans-serif}a{color:var(--accent);text-underline-offset:.2em;overflow-wrap:anywhere}a:hover{text-decoration-thickness:2px}header{background:var(--hero);color:var(--heroink);padding:48px max(22px,calc((100% - 980px)/2)) 44px}header small{letter-spacing:.12em;font-size:13px}h1{font-size:clamp(29px,5vw,48px);line-height:1.3;letter-spacing:-.03em;max-width:760px;margin:18px 0}header p{max-width:760px;margin:16px 0 0;opacity:.9}.chips{display:flex;flex-wrap:wrap;gap:10px;margin-top:24px}.chips span{font-size:13px;border:1px solid #6e9499;border-radius:100px;padding:4px 12px}.wrap{max-width:1024px;margin:auto;padding:28px 22px 64px}.intro{border-left:4px solid var(--accent);padding:12px 20px;background:var(--soft);margin-bottom:24px}.jump{display:flex;gap:12px;flex-wrap:wrap;margin:22px 0}.jump a,button{border:1px solid var(--line);border-radius:8px;padding:9px 14px;background:var(--paper);color:var(--accent);font:inherit;font-size:15px;cursor:pointer;text-decoration:none}.jump a:first-child{background:var(--accent);color:var(--paper)}article{background:var(--paper);padding:10px 34px 28px;border-radius:14px}h2{font-size:25px;line-height:1.4;margin:44px 0 20px;padding-top:12px;border-top:1px solid var(--line);scroll-margin-top:18px}h3{font-size:20px;margin:26px 0 12px}p{margin:14px 0}li{margin:8px 0}ul,ol{padding-left:1.45em}table{border-collapse:collapse;width:100%;font-size:15px;margin:22px 0}th,td{text-align:left;padding:13px 10px;border-bottom:1px solid var(--line);vertical-align:top;overflow-wrap:anywhere}th{background:var(--soft);font-weight:600}code{font-size:.9em;overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.75 ui-monospace,monospace;background:var(--bg);padding:18px;border-radius:8px}details{border-bottom:1px solid var(--line);padding:15px 0}summary{cursor:pointer;font-weight:600;padding:4px 0;overflow-wrap:anywhere}details button{margin:16px 0 0}nav{display:flex;gap:10px 20px;flex-wrap:wrap;padding:16px 0;font-size:14px}footer{margin:28px 0 0;color:var(--muted);font-size:14px}.status{color:var(--muted);font-size:14px;min-height:25px}.sources{font-size:14px;color:var(--muted)}
@media(max-width:650px){header{padding:30px 20px}.wrap{padding:20px 14px 44px}article{padding:4px 18px 22px}h2{font-size:23px;margin-top:34px}table,tbody,tr,td{display:block}thead{display:none}tr{padding:12px 0;border-bottom:1px solid var(--line)}td{padding:6px 0;border:0;font-size:16px}td:before{content:attr(data-label);display:block;font-size:12px;color:var(--muted);font-weight:600}th{display:none}pre{padding:14px;font-size:14px}button{min-height:44px}.jump a{flex:1 1 140px;text-align:center}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}@media print{header{background:none;color:#000}.jump,nav,button{display:none}article{padding:0}details>pre{display:block}}
</style></head><body>
<header><small>游泳内容研究 / 2026.09.19</small><h1>让真实课堂，<br>持续带来新学员。</h1><p>保留成果证明，增加单问题教学，用真实学习过程与本地答疑承接咨询。先把教学项目整理正确，再让剪辑自动执行。</p><div class="chips"><span>本账号11条样本</span><span>8条视频 · 192帧实看</span><span>3个教学账号对照</span><span>含可复制提示词</span></div></header>
<main class="wrap"><div class="intro"><strong>本轮最重要的调整</strong><br>序号跟着教学项目走：同一项深水探底不因两段镜头变成两项；序号与名称同一行。视频类型、剪辑风格、专业术语分别维护。</div>
<div class="jump"><a href="#section-0">先看结论</a><a href="#prompts">复制提示词</a><a href="#section-7">教练拍什么</a></div>
<details><summary>查看报告目录</summary><nav>''' + nav + '''<a href="#prompts">提示词全文</a><a href="#delivery">交付与接续</a></nav></details>
<article>''' + body + '''<h2 id="prompts">提示词与拍摄清单 · 可直接复制</h2><p>先选视频类型，再带入本批素材与最新要求。所有文本均有GitHub版本记录；以下是本轮调教后的内容，不是旧v6的生成依据。</p>''' + ''.join(prompts) + '''<p class="status" id="copy-status" aria-live="polite"></p>
<h2 id="delivery">交付与接续</h2><p><a href="https://github.com/makewheels/video-editing/pull/3">GitHub PR #3：提示词、研究证据与阶段任务</a>（未合并）。后续任务、专业术语与项目分组实现缺口均已记录，下一次可以直接接续。</p>
<p>剪辑归档：<code>oss://video-editing-media/batches/20260918-204846-swimming/</code>。原素材、参考片、v4/v5/v6和早期成片已分目录保存；v2/v3尚未找到。以后每版视频及每轮提示词调教都进入同批目录。</p>
<p><a href="https://oneclick.video/watch/2UGS25">旧v6动画编号版播放页</a>：当前复查页面、匿名访问和HLS均正常，用户报告的手机播放故障尚未复现；该片仍有已记录的项目去重与字幕问题，不是本次纠正后的成片。</p>
<p class="sources">研究来源：各段已链接原作品；公开样本与抽帧时间保存在GitHub的docs/research目录。公开累计数据不是后台转化数据；未完成全账号普查、完整音频听辨或手机真机验收。没有保证爆款，也没有把提示词文档等同于无人值守剪辑服务已经上线。</p></article>
<footer>临时分享报告 · production对象存储 · 无登录、无追踪、无第三方页面资源。请保留来源与采样边界。界面支持窄屏与深色模式；播放故障和后续工程修改独立跟进。</footer></main>
<script>
for(const button of document.querySelectorAll('[data-copy]')){button.addEventListener('click',async()=>{const text=document.getElementById(button.dataset.copy).textContent;try{await navigator.clipboard.writeText(text);document.getElementById('copy-status').textContent='已复制，可以粘贴到剪辑任务中。';}catch{document.getElementById('copy-status').textContent='浏览器未允许复制，请长按文本选择复制。';}});}
</script></body></html>'''
    output.write_text(page, encoding='utf-8')
    return len(page.encode())


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print('bytes', build(args.output))
