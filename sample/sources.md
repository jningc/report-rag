# 样本

每份招标 PDF 配一份同名的虚构公司文件。公司不对应任何真实企业，都故意缺一两项招标要求的资质。PDF 不进 Git。

| 招标文件 | 公司情况 | 项目 |
|---|---|---|
| `beijing_road.pdf` | `beijing_road_company.yaml` | 北京东城道路监理 |
| `chongzuo_green.pdf` | `chongzuo_green_company.yaml` | 崇左龙州八角低产林改造 |
| `wenling_video.pdf` | `wenling_video_company.yaml` | 温岭雪亮工程视频共享整合接入 |

核对时 PDF 和公司文件成对使用，例如：

```bash
python main.py check sample/chongzuo_green.pdf sample/chongzuo_green_company.yaml
python main.py check sample/wenling_video.pdf sample/wenling_video_company.yaml
```

网页和 `python main.py check` 不写公司文件时，默认用 `beijing_road_company.yaml`。

## 下载

浏览器打开即为 PDF，开标已过，只作样本。

```bash
mkdir -p sample
curl -L -o sample/beijing_road.pdf "http://www.ccgp-beijing.gov.cn/content_file/xxgg/qjxxgg/qjzbggs/2026/8/19681edf7a4e471e99eb628a05805c7e.pdf"
curl -L -o sample/chongzuo_green.pdf "https://obs.gcy.zfcg.gxzf.gov.cn/guangxi-xc-gov-open-doc/1024FPA/451402/10014664766/20268/6040c2cf-2fd4-4aa1-b3b9-464f349736e6.pdf"
curl -L -o sample/wenling_video.pdf "https://zjjcmspublic.oss-cn-hangzhou-zwynet-d01-a.internet.cloud.zj.gov.cn/jcms_files/jcms1/web2760/site/attach/-1/2501270936161774774.pdf"
```
