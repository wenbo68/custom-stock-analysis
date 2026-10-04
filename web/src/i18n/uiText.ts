import { ko } from './uiText.ko';

// The languages the page speaks. The backend's table (src/languages.py)
// lists the same codes; add a language in both places.
export type UiLanguage = 'zh' | 'en' | 'ko';

const zh = {

  'language.menu': '界面语言选项',
  'language.toggle': '切换界面语言',
  'language.uiLanguage': '语言',

  // 模式菜单（2026-09-26）：手动分析页，或驱动它的智能体。
  'mode.agentic': '智能体',
  'mode.manual': '手动',
  'mode.menu': '模式选项',
  'mode.mode': '模式',
  'mode.toggle': '切换模式',

  'theme.color': '颜色',
  'theme.dark': '深色',
  'theme.light': '浅色',
  'theme.menu': '主题模式',
  'theme.system': '跟随系统',
  'theme.toggle': '切换主题',

  'tiered.form.market.cn': 'A 股',
  'tiered.form.market.hk': '港股',
  'tiered.form.market.jp': '日股',
  'tiered.form.market.kr': '韩股',
  'tiered.form.market.tw': '台股',
  'tiered.form.market.us': '美股',

  'tiered.queued':
    '排队等待空闲名额。服务器同时只运行少量分析，轮到时会自动开始，无需再点开始。',
  'tiered.running': '分析中（约 2-5 分钟：抓取数据、检索新闻、AI 综合）…',
  'tiered.error.title': '分析失败',
  'tiered.score': '评分',
  'tiered.levels.entry': '入场',
  'tiered.levels.stopLoss': '止损',
  'tiered.levels.target': '目标',
  'tiered.dataReport.technicals': '技术面',
  'tiered.dataReport.fundamentals': '基本面',
  'tiered.dataReport.macro_economy': '宏观经济',
  'tiered.dataReport.positioning': '持仓结构',
  'tiered.dataReport.company_news': '公司新闻',
  'tiered.dataReport.world_news': '世界新闻',
  'tiered.warnings': '警告',
  // 数据说明弹窗的固定关键词表（2026-07-24）：每条说明以其中一个开头，
  // 由 altWarningText.ts 按规则确定，不由 AI 生成。盈亏比一条复用
  // 交易计划警告弹窗的 'tiered.warnKey.reward_below_goal'。
  'tiered.warning.key.missingData': '数据缺失',
  'tiered.warning.key.fetchFailed': '抓取失败',
  'tiered.warning.key.citations': '引用无效',
  'tiered.warning.key.aiReply': 'LLM 回复无效',
  'tiered.warning.key.levels': '价位问题',
  'tiered.warning.key.outlook': '无展望',
  'tiered.warning.key.vote': '投票问题',
  'tiered.warning.key.deepAnalysis': '无可用投票项',
  'tiered.warning.key.riskCheck': '计划复核未完成',
  'tiered.warning.key.settings': '设置无效',
  'tiered.warning.key.newsCap': '新闻已截断',
  // 无规则匹配时的兜底关键词——所有用户可见的“数据说明”一律叫
  // “警告”（所有者要求 2026-08-25）。
  'tiered.warning.key.other': '未知问题',
  'tiered.summaryGroup': '总结',
  'tiered.warning.barsLoadFailed': '日线行情加载失败，因此所有技术面数字都无法计算。',
  'tiered.warning.yahooSummaryFailed': 'Yahoo Finance 摘要页加载失败，相关字段为空。',
  'tiered.warning.holdersFailed': '大型基金持仓名单加载失败，前十大集中度及其数据日期为空。',
  'tiered.warning.insiderFetchFailed': '内部人买卖申报加载失败，内部人交易各行为空。',
  'tiered.warning.optionsFetchFailed': '期权数据加载失败，期权各行为空。',
  'tiered.warning.earningsDateFailed': '下一次季度财报日期查询失败，依赖该日期的字段为空。',
  'tiered.warning.earningsHistoryFailed': '历史季度财报记录加载失败，超预期次数与历史财报日涨跌为空。',
  'tiered.warning.reactionBarsFailed': '用于测算历史财报日股价反应的行情加载失败，相关行为空。',
  'tiered.warning.epsTrendFailed': '分析师盈利预期历史加载失败，30 天预期变化一行为空。',
  'tiered.warning.epsRevisionsFailed': '分析师预期调整人数加载失败，30 天上调/下调人数两行为空。',
  'tiered.warning.releaseCalendarFailed': '{label} 的发布日历加载失败，其下次发布日期为空。',
  'tiered.warning.benchmarkBarsFailed': '大盘指数行情加载失败，无法将本股与大盘比较。',
  'tiered.warning.newsHeadlinesFailed': '公司新闻抓取失败，本报告没有新闻标题。新闻源返回：{detail}',
  'tiered.warning.sectorBarsFailed': '行业基金（{ticker}）行情加载失败，行业对比各行为空。',
  'tiered.warning.providerCrashed': '{dataReport} 数据采集出现异常，本次运行缺少整个板块。',
  'tiered.warning.deepAnalysisCallFailed': '深度分析的 LLM 调用失败，本次运行没有展望。',
  'tiered.warning.planReviewCallFailed': '交易计划复核的 LLM 调用失败，沿用计算出的原始计划。',
  'tiered.warning.planReviewSkipped': '交易计划复核需要的 AI 密钥未配置，沿用计算出的原始计划。',
  'tiered.warning.insufficientHistory': '该股票只有 {bars} 天行情，少于指标所需的 {min} 天，技术面分析已跳过。',
  'tiered.warning.shortDailyHistory': '只取到 {bars} 天行情（整年约 {year} 个交易日），因此一年高点、低点和区间反映的是现有历史，而非完整一年。',
  'tiered.warning.shortWeeklyHistory': '只取到 {bars} 周行情（周线分析需要 {target} 周），周线趋势不可靠。',
  'tiered.warning.benchmarkNotConfigured': '该市场未配置大盘指数，无法将本股与大盘比较。',
  'tiered.warning.benchmarkShort': '大盘指数只有 {bars} 天历史，不足以判断大盘趋势或比较涨跌幅。',
  'tiered.warning.benchmarkShortRegime': '大盘指数没有大盘趋势判断所需的 200 天历史。',
  'tiered.warning.noImpliedVol': '期权交易所未公布 30 天预期波动数据，隐含波动率一行为空。',
  'tiered.warning.noOptionsStockPrice': '期权交易所未公布股价，无法计算预期财报日涨跌幅。',
  'tiered.warning.reportDateUnknown': '下一次季度财报日期未知，无法计算预期财报日涨跌幅。',
  'tiered.warning.reportDateUnreadable': '下一次季度财报日期返回的格式系统无法识别，无法计算预期财报日涨跌幅。',
  'tiered.warning.reportTooFarExact': '下一次季度财报在 {days} 天以后——超过了 {max} 天。那么远的期权价格主要反映日常波动而非财报本身，因此不显示财报日涨跌幅。',
  'tiered.warning.ratioMissingIngredient': '该比值需要 {field}，本次运行中该字段为空。',
  'tiered.warningF.daysUntilReport': '距下次季度财报的天数',
  'tiered.warning.noAtmQuotes': '财报后首个到期的期权合约没有可用的买卖报价，无法计算预期财报日涨跌幅。',
  'tiered.warning.noPostReportExpiry': '已取到的期权到期日均早于下一次财报，无法计算预期财报日涨跌幅。',
  'tiered.warning.noListedOptions': '该股票没有挂牌期权，没有期权数据可显示。',
  'tiered.warning.noShortInterest': 'Yahoo Finance 未公布该股票的做空数据，做空各行为空。',
  'tiered.warning.noOwnership': 'Yahoo Finance 未公布该股票的持股数据，持股各行为空。',
  'tiered.warning.noEarningsHistory': '未取到该股票的历史季度财报记录，超预期次数与历史财报日涨跌为空。',
  'tiered.warning.tooFewReports': '已加载的行情区间内只有 {count} 次历史财报，不足以求财报日平均涨跌幅。',
  'tiered.warning.fredKeyMissing': '经济数据服务（FRED）未配置访问密钥，无法加载经济数据。',
  'tiered.warning.noReleaseDate': '{label} 尚未公布下一次发布日期。',
  'tiered.warning.fomcTableExhausted': '内置的美联储议息会议日期表已用尽，下一次利率决议日期为空。',
  'tiered.warning.sectorUnknown': '该公司所属行业（它所在的行业大类）未知，行业对比各行为空。',
  'tiered.warning.sectorNoEtf': '该公司所属行业尚未配置对应的行业基金（目前仅支持美股行业），行业对比各行为空。',
  'tiered.warning.sectorNeedsBenchmark': '行业对比以大盘涨跌幅为基准，而该数据缺失，行业对比各行为空。',
  'tiered.warning.sectorShort': '行业基金（{ticker}）只有 {bars} 天历史，不足以比较涨跌幅，行业对比各行为空。',
  'tiered.warning.noClosePrice': '没有收盘价，无法计算交易计划。',
  'tiered.warning.noEntryAnchor': '买入价所依据的价格——50 日均线、200 日均线、最近支撑位——都不可用，无法计算交易计划。',
  'tiered.warning.noTechnicalsForLevels': '缺少技术面数据，无法计算交易计划。',
  'tiered.warning.duplicateAdjust': 'AI 对{level}提出了两次调整，保留第一次，忽略第二次。',
  'tiered.warning.planAdjustDropped': 'AI 对{level}提出的调整无法在报告中找到数据依据，该调整已丢弃。',
  'tiered.warning.planReplyProblem': 'AI 的计划复核回复中有系统无法使用的内容，该部分已忽略。',
  'tiered.warning.planNoConverge': 'AI 提出的每一次调整都未通过风险检查，全部丢弃，沿用计算出的原始计划。',
  'tiered.warning.noGradableFields': '没有可供列出者打分的报告字段，本次运行没有展望。',
  'tiered.warning.noEvidenceToVote': '没有报告数据送达列出者，无内容可判断，请重新运行该股票。',
  'tiered.warning.rewardRiskDefaulted': '盈亏比设置必须大于 1，所填数值已忽略，改用默认值。',
  'tiered.warning.adjustUnknownLevel': 'AI 提出的调整对象不属于交易计划中的任何价位，已忽略。',
  'tiered.warning.downtrend': '收盘价已到 50 日均线或以下——逆势低吸的下行风险更高。',
  'tiered.warning.trendCheckSkipped': '缺少 50 日均线数据，趋势检查已跳过。',
  'tiered.warning.summaryLinksDropped':
    '总结中有引用经多次修正仍未通过代码校验——相关数值仍然展示，但没有链接。',
  'tiered.warning.optionsOiMissing':
    '数据源返回的期权未平仓量缺失或为零——Put/Call 未平仓比和总未平仓量留空，不显示误导性的 0。',
  'tiered.warning.optionsVolumeMissing':
    '数据源返回的期权成交量缺失或为零——Put/Call 成交量比留空，不显示误导性的 0。',
  'tiered.warning.insiderRowsMissing':
    'Yahoo 没有返回任何内部人交易记录——无法区分“确实没人交易”和“数据缺失”，因此内部人板块留空。',
  // 新闻筛选各阶段（评分/合并/排序/摘要）失败时的降级说明——每一步
  // 失败都只降低卡片质量，绝不丢新闻。
  'tiered.warning.newsJudgeFailed':
    'LLM 给每条新闻评相关性和重要性的回复缺失或无法解读，所有文章未经评分全部保留。',
  'tiered.warning.newsJudgeMissing':
    'AI 的新闻评分回复漏掉了 {count} 条文章——这些文章未经评分而保留。',
  'tiered.warning.newsGroupFailed':
    'LLM 用来把同一事件的多篇报道合并成一条的回复缺失或无法解读，因此没有做合并——同一件事可能重复出现。',
  'tiered.warning.newsGroupPartial':
    'AI 的同事件合并回复漏掉了 {count} 条文章——这些文章各自作为独立事件保留。',
  'tiered.warning.newsRankFailed':
    'LLM 按重要性给事件排序的回复缺失或无法解读，事件改按重要性得分顺序展示。',
  'tiered.warning.newsRankPartial':
    'AI 的排序回复漏掉了 {count} 个事件——这些事件按重要性得分顺序排在末尾。',
  'tiered.warning.newsSummaryFailed':
    'LLM 写一句话摘要的回复缺失或无法解读，改为显示新闻源自带的原文摘要。',
  'tiered.warning.newsSummaryMissing':
    'AI 的摘要回复漏掉了 {count} 条文章——这些条目显示新闻源自带的原文摘要。',
  'tiered.warning.newsTrimmed':
    '新闻高峰期：符合条件的事件超过卡片上限，排名在前 {max} 之外的 {count} 个事件未展示。',
  'tiered.group.trend': '价格与趋势',
  'tiered.group.momentum': '动量',
  'tiered.group.volatility': '波动与区间',
  'tiered.group.structure': '价格结构',
  'tiered.group.volume': '成交量',
  'tiered.group.meta': '数据与评分',
  'tiered.group.reportInfo': '报告信息',
  'tiered.group.earnings': '财报',
  'tiered.group.other': '其他',
  'tiered.warning.fetchFailed': '一篇新闻（{domain}）未能下载，因此没有采用。',
  'tiered.warning.fundamentalsUnavailable': '美国证监会（SEC）官方财报数据未能加载，部分基本面数字可能缺失。',
  'tiered.warning.valuationUnavailable': '来自 Yahoo Finance 的估值指标未能加载。',
  'tiered.warning.macroUnavailable': '一项经济指标（{series}）未能从 FRED 数据库加载。',
  'tiered.warning.indicatorNoHistory': '价格历史不足，无法计算该数值。',
  'tiered.warning.macroFieldMissing': '数据源返回的数据不足，无法计算该数值。',
  'tiered.warning.adjustmentRejected': 'AI 想微调{level}，但建议不符合规则，已保留公式算出的数字。',
  'tiered.warning.stopFallback': '公式算出的止损价不可用，改用了基于波动幅度（ATR）的止损。',
  'tiered.warning.noAtrStop': '缺少波动幅度数据（ATR），无法计算止损价。',
  'tiered.warning.noAtrStopTarget': '缺少波动幅度数据（ATR），止损价和目标价都无法计算。',
  'tiered.warning.noEntryNoStop': '没有可用的买入价，因此无法设置止损。',
  'tiered.warning.summaryFailed': '深度分析的文字总结生成失败——公式算出的展望不受影响。',
  'tiered.warning.badSetting': '有一项仓位设置不是数字，已忽略。',
  'tiered.help.entry': '理想买入价。\n通常靠近支撑位——此前买盘出现过的价位。',
  'tiered.help.stopLoss': '安全出口。\n跌到这里说明判断错了——在此卖出可控制亏损。',
  'tiered.help.target': '获利目标。\n分析建议在此卖出、锁定收益。',
  'tiered.empty': '输入股票代码开始一次分层分析。',
  'tiered.history.title': '运行历史',
  'tiered.status.queued': '排队中',
  'tiered.status.queuedAt': '排队中（{position}）',
  'tiered.status.running': '分析中',
  'tiered.status.done': '已完成',
  'tiered.status.failed': '失败',
  'tiered.help.tier':
    '层级 1（初步分析）：六份数据报告加一次给出展望的 LLM 调用。\n层级 2（深度分析）：跳过这次单独调用，改由两位 LLM 列出者给每个报告字段打分、生成投票项，再逐项投票定分——更慢但更扎实。\n（层级 3 已下线。）',
  'tiered.llmUsage': '本次运行 LLM 调用 {calls} 次（{tokens} tokens）',
  'tiered.help.llmUsage':
    '本次运行发起的 LLM 调用次数（每次即向大语言模型 API 发起一次请求）与 token 总量（token 是计费单位）。\n点击可展开每次调用的输入与输出。',
  'tiered.transcript.call': '第 {n} 次 LLM 调用',
  'tiered.transcript.for': '用于',
  'tiered.transcript.llm': 'llm',
  'tiered.transcript.time': '耗时',
  'tiered.transcript.tokenCount': '{n} tokens',
  'tiered.transcript.loading': '加载中…',
  'tiered.transcript.error': '无法加载对话记录：{error}',
  'tiered.transcript.empty': '该运行的对话记录已过期（保留 14 天）。',
  'tiered.transcript.input': '输入',
  'tiered.transcript.output': '输出',
  'tiered.transcript.failed': '调用失败：{error}',
  'tiered.transcript.noReply': '（无回复）',
  'tiered.transcript.callLoading': '加载中…',
  'tiered.transcript.callError': '无法加载这次调用：{error}',
  'tiered.kind.formula': '公式',
  'tiered.kind.adjustment': '调整',
  'tiered.kind.whyBlank': '为何为空',
  'tiered.kind.warnings': '警告',
  'tiered.blankFallback': '本次运行中该字段没有数值——计算它所需的数据不可用。',
  'tiered.levelModal.noBase': '本次运行缺少计算该价位所需的数据，没有公式基准。',
  'tiered.levelModal.references': '参考依据',
  'tiered.help.deepAnalysis':
    '两位 LLM 列出者各自独立地给六份数据报告（技术面、基本面、持仓面、宏观经济、公司新闻、世界新闻）的每个字段打上看多、看空或中性标签；每个看多或看空标签变成一条单句投票项，并附 1-5 的评分。\n每条投票项引用的数值都由代码逐一校验：数值必须与报告显示的完全一致、且出现在句子里；不合格的引用会退回给列出者修正（最多 3 次），仍失败的整条划线剔除。\n代码合并两份评分表，每条投票项按多数票决定去留（最多 3 票）：列出者自动算一张有效票，两位列出者标签相同的字段直接确认；只有一位列出的投票项由核查员投第二票；1 比 1 平局时由决胜票裁定。\n代码按评分加总看多/看空投票项算出展望分——LLM 不经手任何数字。最后一次 LLM 调用根据投票结果撰写摘要，得分不依赖于它。',
  'tiered.deepAnalysis.noOutlook': '深度分析未产生展望——请重新运行（详见警告）。',
  'tiered.tree.bullish': '看多',
  'tiered.tree.bearish': '看空',
  'tiered.tree.valid': '有效',
  'tiered.tree.invalid': '无效',
  'tiered.tree.scores': '评分',
  'tiered.tree.finalScore': '最终展望分',
  'tiered.tree.title': '投票项',
  'tiered.tree.loading': '加载投票项…',
  'tiered.tree.loadError': '无法加载投票项：{error}',
  'tiered.tree.howItWorks': '规则说明',
  'tiered.tree.explain1':
    '两位 LLM 列出者各自独立地给六份数据报告（技术面、基本面、持仓面、宏观经济、公司新闻、世界新闻）里的每一个字段打上看多、看空或中性标签，互不知晓对方的结果。',
  'tiered.tree.explain2':
    '看多或看空标签会变成一条引用该字段数值的单句投票项；中性标签不产生任何投票项。每个经手投票项的列出者或核查员还会给它打 1-5 的评分（1 = 非常次要，5 = 非常重要）并说明理由。',
  'tiered.tree.explain3':
    '代码逐条核对投票项引用的数值；不合格的引用退回给列出者修正（最多 3 次），仍失败的整条划线剔除，不计入任何得分。',
  'tiered.tree.explain4':
    '代码合并两份评分表。两位列出者给出相同标签的字段合成一条有两位列出者的投票项——已经 2 比 0 达成一致，因此没有任何检查标记。',
  'tiered.tree.explain5':
    '只有一位列出者列出的投票项（或两位列出者标签相反的字段）由核查员检查——即投票项后的 ✓ 或 ✗；点击标记可查看理由。',
  'tiered.tree.explain6':
    '若该检查为无效，该投票项 1 比 1 平票，再由一次 LLM 调用投出决胜票——即第二个标记。没有决胜票的平票不计入得分。',
  'tiered.tree.explain7':
    '带有两个 ✗ 的投票项被否决并划线；未划线的投票项全部计入，其评分取它收到的全部 1-5 评分的中位数。点击评分可查看理由。',
  'tiered.tree.explain8':
    '代码算出最终展望分：10 × 看多投票项的评分和 ÷ 全部计入投票项的评分和。低于 4 看空，4–6 中性，高于 6 看多。没有任何 LLM 写分数。',
  'tiered.tree.explain9':
    '最后一次 LLM 调用根据投票后的投票项清单撰写摘要；摘要里的数字同样经过引用核对，即使摘要失败，代码算出的得分也不受影响。',
  'tiered.tree.codeCheck': '代码检查结果',
  'tiered.warning.listerDegradedRole': '{role}——评分表连续不合规，本次只使用另一位列出者的评分表。',
  'tiered.warning.sheetsVoided': '两位列出者的评分表连续不合规——深度分析作废。',
  'tiered.warning.noOutlook': '深度分析未能得出展望——请重新运行该股票。',
  'tiered.warning.preliminaryNoOutlook': '初步分析未产生展望——请重新运行该股票。',
  'tiered.warning.preliminaryCallFailed': '初步分析的 LLM 调用失败，本次运行没有展望。',
  'tiered.warning.preliminaryReplyRejected': '初步分析的回复无法使用（{problem}），已重新询问。',
  'tiered.warning.checkDegraded': '复核投票连续不合规——各条投票项仅按列出者一票计入。',
  'tiered.warning.tiebreakDegraded': '决胜投票连续不合规——平票的投票项按未决处理，不计入得分。',
  'tiered.warning.voteDiscarded': '一张投票的引用经多次修正仍未通过代码校验——该票作废。',
  'tiered.warning.unresolved': '某条投票项 1 比 1 平票且没有决胜票——按未决处理，不计入得分。',
  'tiered.warning.allConfirmed': '每条投票项都被两位列出者独立列出——无需复核投票。',
  'tiered.warning.struckBullet':
    '某条投票项的引用经 3 次修正仍未通过代码校验——该条已划线剔除，不计入任何得分。',
  'tiered.warning.fixRoundLost': '一次引用修正回复不可读——浪费了一轮修正机会。',
  'tiered.warning.stageRetriedRole': '{role}——第一次回复不合规，重试一次后通过。',
  'tiered.warning.stageInvalidRole': '{role}——重试后回复仍不合规。',
  'tiered.role.checkRound': '复核投票',
  'tiered.role.decidingRound': '决胜投票',
  'tiered.role.reportOutline': '报告撰写',
  'tiered.role.newsJudge': '新闻相关性判定',
  'tiered.role.newsGrouping': '同一事件新闻归并',
  'tiered.role.newsRanking': '新闻重要性排序',
  'tiered.role.newsSummary': '新闻摘要撰写',
  'tiered.role.preliminaryAnalysis': '初步分析',
  'tiered.role.planReview': '交易计划复核',
  'tiered.role.citationFix': '{role}（引用修正）',
  'tiered.warning.stageWrongLanguageRetried': '{role}——第一次回复不是{language}，重新询问后已改正。',
  'tiered.warning.stageWrongLanguageKept': '{role}——重新询问 {retries} 次后回复仍不是{language}，按原文显示。',
  'tiered.languageName.en': '英文',
  'tiered.languageName.zh': '简体中文',
  'tiered.warning.emptyLedger': '没有可计入的投票项，最终得分默认取中性 5。',
  'tiered.warning.thinBase': '列出者最初的投票项大多未能成立——得分建立在较薄的基础上。',
  'tiered.help.deepAnalysisScore':
    '深度分析得出的最终展望分，满分 10，保留两位小数。\n0 = 强烈看空，5 = 中性，10 = 强烈看多。\n低于 4 看空，4–6 中性，高于 6 看多。\n完全由代码算出：得分 = 10 × 看多投票项的评分和 ÷ 全部投票项的评分和，只统计经受住检验的投票项——见「投票项」底部的「评分」。',
  'tiered.help.sizing':
    '固定算术，无 AI 参与。\n每个数字都能点击跳到它在本报告中出现的位置。\n结果向下取整为整数股，单只股票最多占用本金的 25%。',
  'tiered.form.ticker': '代码',
  'tiered.form.tier': '层级',
  'tiered.form.capital': '本金',
  'tiered.form.capitalCurrency': '本金: {currency}',
  'tiered.form.risk': '单笔风险: %',
  'tiered.form.title': '新运行',
  'tiered.form.start': '开始',
  'tiered.form.noticeTitle': '提示',
  'tiered.form.needTickerFirst': '请先选择股票代码——本金使用该股票所在市场的货币。',
  'tiered.form.errorTitle': '错误',
  'tiered.form.missingIntro': '以下必填项尚未填写：',
  'tiered.form.duplicateRunning':
    '完全相同的 {ticker} 分析正在运行（本金、单笔风险、盈亏比、最长持有、层级都一样），已在下方运行历史中展开。请等它完成，或改动其中一项后再开始。',
  'tiered.form.duplicateQueued':
    '完全相同的 {ticker} 分析已在排队（本金、单笔风险、盈亏比、最长持有、层级都一样），已在下方运行历史中展开。它会自动开始；请等它完成，或改动其中一项后再开始。',
  'tiered.form.req.ticker': '代码',
  'tiered.form.req.tier': '层级',
  'tiered.form.req.capital': '本金',
  'tiered.form.req.risk': '单笔风险',
  'tiered.form.req.reward': '盈亏比',
  'tiered.form.req.hold': '最长持有',
  'tiered.form.tierOption1': '1：初步分析',
  'tiered.form.tierOption2': '2：深度分析',
  'tiered.form.tickerPh': '输入代码…',
  'tiered.form.tierPh': '输入层级…',
  'tiered.form.capitalPh': '输入本金…',
  'tiered.form.riskPh': '输入风险…',
  'tiered.form.reward': '盈亏比: x',
  'tiered.form.rewardPh': '输入盈亏比…',
  'tiered.form.lowRewardWarn':
    '盈亏比低于 1.5 意味着交易几乎不足以覆盖风险——常见要求至少 1.5×。本次运行仍会按你的 {value}× 目标进行。',
  'tiered.help.reward':
    '你要求这份计划的盈亏比（潜在盈利是风险的几倍）。必填，默认 2。\n目标价 = 入场价 + 盈亏比 × 风险；若上方阻力把目标压到低于你要求的倍数，计划会附警告（低于 1.5 的硬下限则直接不给计划）。',
  'tiered.form.hold': '最长持有: 周',
  'tiered.form.holdPh': '输入最长持有…',
  'tiered.help.hold':
    '你计划最长持有这笔交易多久。必填，默认 2 周。\n同一个数字会同时交给 AI（判断哪些证据在这个时间范围内重要）、显示在报告里、并作为前向测试的评分窗口——AI、你和测试始终对齐同一个时间范围。',
  'tiered.form.marketOpenTitle': '市场交易中',
  'tiered.form.marketOpenTrading':
    '{market}正在交易。本应用只分析已收盘的完整交易日，今天还没有可分析的数据。',
  'tiered.form.marketOpenHours':
    '今日交易时段：{open}–{close}（市场当地时间），相当于你时区的 {openLocal}–{closeLocal}。',
  'tiered.form.marketOpenMixedData':
    '「仍要运行」将分析上一个完整交易日：技术面报告只使用截至该日收盘的数据，但新闻等其他数据可能是实时的——报告内部可能混合两个时点的数据，出现不一致。',
  'tiered.form.marketOpenBestWindow':
    '另外，即使已收盘，数据源也可能落后实时数据最多 30 分钟，且一次运行本身需要时间——建议在收盘 30 分钟后、下次开盘 30 分钟前使用本应用。',
  'tiered.form.runAnyway': '仍要运行',
  'tiered.pill.ticker': '代码: {value}',
  'tiered.pill.tier': '层级: {value}',
  'tiered.pill.capital': '本金: {value} {currency}',
  'tiered.pill.risk': '单笔风险: {value}%',
  'tiered.pill.reward': '盈亏比: {value}×',
  'tiered.pill.hold': '最长持有: {value} 周',
  'tiered.pill.capitalMin': '本金下限: {value}',
  'tiered.pill.capitalMax': '本金上限: {value}',
  'tiered.pill.riskPctMin': '单笔风险下限: {value}%',
  'tiered.pill.riskPctMax': '单笔风险上限: {value}%',
  'tiered.pill.dateMin': '日期下限: {value}',
  'tiered.pill.dateMax': '日期上限: {value}',
  'tiered.pill.rewardRatioMin': '盈亏比下限: {value}×',
  'tiered.pill.rewardRatioMax': '盈亏比上限: {value}×',
  'tiered.filter.tickerPh': '输入代码…',
  'tiered.filter.capital': '本金',
  'tiered.filter.risk': '单笔风险: %',
  'tiered.filter.date': '日期: yyyy/mm/dd',
  'tiered.filter.tier': '层级',
  'tiered.filter.tierPh': '输入层级…',
  'tiered.filter.holdPh': '输入最长持有…',
  'tiered.filter.reward': '盈亏比: ×',
  'tiered.filter.min': '下限',
  'tiered.filter.max': '上限',
  'tiered.history.shares': '{value} 股',
  'tiered.history.tier': '层级 {value}',
  'tiered.history.hold': '{value} 周',
  // 运行列表的表头（各列含义）。
  'tiered.history.h.ticker': '代码',
  'tiered.history.h.capital': '本金',
  'tiered.history.h.risk': '单笔风险',
  'tiered.history.h.reward': '盈亏比',
  'tiered.history.h.hold': '最长持有',
  'tiered.history.h.tier': '层级',
  'tiered.history.h.status': '状态',
  'tiered.history.h.outlook': '展望',
  'tiered.history.h.date': '日期',
  'tiered.history.first': '第一页',
  'tiered.history.prev': '上一页',
  'tiered.history.next': '下一页',
  'tiered.history.last': '最后一页',
  'tiered.history.none': '没有符合筛选的运行',
  'tiered.history.loading': '加载报告…',
  'tiered.history.delete': '删除这次分析',
  'tiered.history.cancel': '取消本次运行',
  'tiered.history.deleteAsk': '删除这次分析及其 LLM 记录？此操作无法撤销。',
  'tiered.history.cancelAsk': '把这次分析移出队列？它将不会开始。',
  'tiered.history.confirmDelete': '删除',
  'tiered.history.confirmCancel': '取消运行',
  'tiered.history.keep': '保留',
  'tiered.history.deleting': '删除中…',
  'tiered.history.deleteInProgress': '分析正在进行，无法删除；等它结束后再试。',
  'tiered.history.deleteError': '无法删除：{error}',
  'tiered.dataReports.title': '数据报告',
  'tiered.eventsNone': '近 {count} 天内无记录',
  'tiered.eventsNoneGeneric': '暂无记录',
  'tiered.eventsWindow': '近 {count} 天',
  'tiered.deepAnalysis.title': '深度分析',
  'tiered.rewardBelowGoal':
    '本计划的盈亏比为 {ratio}，低于你要求的 {goal}×——上方阻力压低了目标价。',
  'tiered.roundLevelTitle': '整数关口',
  'tiered.roundLevelBody':
    '{value} 是当前价下方最近的整数价位。它不来自任何数据行——由代码当场算出：挂单常聚集在整数价位，形成较弱的支撑。',
  'tiered.f.capital': '本金',
  'tiered.f.risk': '单笔风险',
  'tiered.f.entry': '入场价',
  'tiered.f.stop': '止损价',
  'tiered.sources': '来源',
  'tiered.levels.computed': '计算值',
  'tiered.levels.adjusted': '调整值',
  'tiered.levels.keep': '不变',
  'tiered.levels.shares': '股数',
  'tiered.levels.warnings': '警告',
  'tiered.warn.none': '无',
  'tiered.warn.downtrend':
    '收盘价（{close}）不高于 60 日均线（{sma60}）——股票处于中期下行趋势，此时入场是逆势买入，进一步下跌的风险更高。',
  'tiered.warn.downtrend_50':
    '收盘价（{close}）不高于 50 日均线（{sma50}）——股票处于中期下行趋势，此时入场是逆势买入，进一步下跌的风险更高。',
  'tiered.warn.earnings_soon':
    '距下次财报仅 {days} 天（{date}），在典型波段持仓期内。技术面判断扛不住财报：一次公告就可能让价格跳空越过任何止损。建议财报前离场，或按跳空风险缩小仓位。',
  'tiered.warn.macro_event_soon':
    '距{event}仅 {days} 天（{date}），在典型波段持仓期内。这是市场层面的跳空风险：一个数字可能让所有股票同时跳动。建议届时缩小仓位，或按跳空风险规划止损。',
  'tiered.warnEvent.rate_decision': '下次官方利率决议',
  'tiered.warnEvent.inflation_data': '下次通胀数据发布',
  'tiered.warnEvent.employment_data': '下次就业数据发布',
  'tiered.warn.gap_atr':
    '若隔夜消息导致跳空低开，开盘价比止损（{stop}）再低 1 个 ATR（{atr}），落在 {atrOpen}——止损单会在该价成交，亏损 {atrLoss}，比计划的 {planned} 多亏 {atrExtra}。',
  'tiered.warn.gap_worst':
    '若重演过去一年最差单日（{worstDayPct}%），开盘价将落在 {worstOpen}，跌破止损（{stop}）——在该价卖出亏损 {worstLoss}，比计划的 {planned} 多亏 {worstExtra}。',
  // 警告公式弹窗里各计算值的名称（也用作公式文字行的变量名）。
  'tiered.warnF.gapOpen': '跳空开盘价',
  'tiered.warnF.gapLoss': '跳空亏损',
  'tiered.warnF.plannedLoss': '计划亏损',
  'tiered.warnF.worstOpen': '最差单日开盘价',
  'tiered.warnF.worstLoss': '最差单日亏损',
  'tiered.warnF.ratio': '盈亏比',
  'tiered.f.shares': '股数',
  'tiered.f.target': '目标价',
  // 每条风险文案开头的固定关键词（由代码根据检查项 id 决定，非 AI 生成）。
  'tiered.warnKey.downtrend': '下行趋势',
  'tiered.warnKey.earnings_soon': '财报临近',
  'tiered.warnKey.macro_event_soon': '宏观事件临近',
  'tiered.warnKey.gap_atr': '隔夜跳空风险',
  'tiered.warnKey.gap_worst': '最差单日跳空风险',
  'tiered.warnKey.reward_below_goal': '盈亏比偏低',
  'tiered.checkKey.downtrend': '下行趋势',
  'tiered.checkKey.liquidity': '流动性',
  'tiered.checkKey.volatility': '波动',
  'tiered.checkKey.stop_vs_support': '支撑位',
  'tiered.reviewFail.title': '为什么维持原计算值',
  'tiered.reviewFail.intro':
    'AI 尝试调整了这份方案，但每次调整后仍有风控检查未通过，因此放弃全部调整，维持按公式计算的方案。',
  'tiered.reviewFail.round': '第 {round} 轮调整后仍触发：{checks}',
  'tiered.help.capital': '你的交易本金，货币跟随股票所在市场。\n股数计算以它为起点。\n会记住，供下次运行使用。',
  'tiered.help.riskPct': '单笔交易你最多接受亏掉本金的百分之几。\n常见为 1-2%。',

  // ---- 展望改版（outlook redesign）----
  'tiered.preliminaryAnalysis.title': '初步分析',
  'tiered.outlook': '展望',
  'tiered.action': '操作',
  'tiered.actionRatio': '当前盈亏比为 {ratio}',
  'tiered.outlook.bullish': '看多',
  'tiered.outlook.neutral': '中性',
  'tiered.outlook.bearish': '看空',
  'tiered.outlook.no_outlook': '无展望',
  'tiered.action.buy_now': '现在买入',
  'tiered.action.buy_later': '稍后再买',
  'tiered.action.no_trade': '不交易',
  'tiered.action.unknown': '重跑——本次运行未产生可用展望',
  'tiered.help.outlook':
    '「展望」是对这只股票本身的判断（看多 / 中性 / 看空），与你是否持有无关。\n「操作」由代码根据展望推出：看多→现在买入（交易计划的盈亏比达到你设定的目标）或稍后再买（低于目标）；中性或看空→不交易。',
  'tiered.help.action':
    '由固定代码规则从展望推出的个人操作建议。\n看多时分两种：交易计划的实际盈亏比达到你设定的目标→「现在买入」；被上方阻力等因素压到低于目标→「稍后再买」（等更好的价位再入场）。',
  'tiered.staleWarning': '本报告来自之前的交易日——请重跑一次以获得最新计划。',
  'tiered.tradePlan.title': '交易计划',
  'tiered.help.plan':
    '由固定公式从价格数据算出的计划价位（不经 LLM）。\n显示内容随「操作」变化：现在买入或稍后再买→完整价位表；不交易→无价位。',
  'tiered.filter.status': '状态',
  'tiered.filter.statusPh': '输入状态…',
  'tiered.pill.status': '状态: {value}',
  'tiered.filter.outlook': '展望',
  'tiered.filter.outlookPh': '输入展望…',
  'tiered.pill.outlook': '展望：{value}',

  'tiered.tree.bullishScoreSum': '看多评分和',
  'tiered.tree.totalScoreSum': '总评分和',

  // ---- 层级 2 详情（v11：1-5 评分 + 评分理由）----
  'tiered.tree.lister': '列出者 {n}',
  'tiered.tree.checker': '核查员 {n}',
  'tiered.tree.validityLine': '结果：{value}',
  'tiered.tree.reasonPrefix': '理由：',
  'tiered.tree.scoreLine': '评分：{value}',
  'tiered.tree.scoresList': '各方评分：{value}',
  'tiered.tree.medianTitle': '评分',
  'tiered.tree.medianLine': '中位数：{value}',

  // 对话页（2026-09-21）：机器人通过应用自己的 API 读取和操作分析。
  'chat.sidebar.title': '历史',
  'chat.new': '新对话',
  'chat.facts.inputs': '用户输入',
  'chat.facts.tokens': '总 tokens',
  'chat.facts.start': '开始日期',
  'chat.facts.end': '结束日期',
  'chat.sidebar.delete': '删除这个对话',
  'chat.sidebar.deleteAsk': '删除这个对话？此操作无法撤销。',
  'chat.sidebar.confirmDelete': '删除',
  'chat.sidebar.keep': '保留',
  'chat.empty.hint':
    '这个 ReAct 智能体由你的主 LLM 驱动。它对本应用有整体的了解，并能调用用户可用的全部 API。注意：它无法访问源代码。',
  'chat.composer.placeholder': 'Enter 发送；Shift+Enter 换行',
  'chat.composer.send': '发送',
  'chat.composer.waitConfirm': '请先回答上面的问题。',
  'chat.step.tool': '第 {n} 步：LLM 决定调用工具',
  'chat.step.say': '第 {n} 步：LLM 决定作答',
  'chat.step.failed': '第 {n} 步：LLM 调用失败',
  'chat.step.toolCall': '第 {n} 步：工具调用',
  'chat.tool.name': '名称',
  'chat.tool.decision': '决定',
  'chat.tool.approve': '同意',
  'chat.tool.decline': '拒绝',
  'chat.tool.status': '状态',
  'chat.tool.status.waiting': '等待中',
  'chat.tool.status.processing': '处理中',
  'chat.tool.status.done': '已完成',
  'chat.tool.status.failed': '失败',
  'chat.tool.approved': '已同意',
  'chat.tool.declined': '已拒绝',
  'chat.tool.truncated': '模型看到的是截短后的副本。',
  'chat.tool.input': '输入',
  'chat.tool.output': '输出',
  'chat.usage': '本步骤使用了 {tokens} tokens',
  'chat.step.noUsage': '本步骤未报告 tokens',
  'chat.transcript.missing': '这条回复没有保存对话记录（2026-09-23 之前的回复没有记录）。',
  'chat.help.usage':
    '这次 LLM 调用用掉的 tokens（计费单位）。每次调用都会重新发送系统提示、工具菜单和整段对话，所以即使一句"hi"也要几千个。\n点击查看这次调用的完整提示词和回复。',
  'chat.notice.toolCallLimit': '机器人已达到单轮工具调用上限，已停止。',
  'chat.notice.wrongLanguage': '这条回复不是所选的语言。',
  'chat.error.busy': '机器人还在处理上一条消息。',
  'chat.error.notConfigured': '未配置模型。请先在 .env 中设置 MAIN_LLM 和 LLM_API_KEY。',
  'chat.error.send': '发送失败：{error}',

} as const;

export type UiTextKey = keyof typeof zh;

const en: Record<UiTextKey, string> = {

  'language.menu': 'UI language options',
  'language.toggle': 'Switch UI language',
  'language.uiLanguage': 'Language',

  // Mode menu (2026-09-26): the manual analysis page, or the agent that drives it.
  'mode.agentic': 'Agentic',
  'mode.manual': 'Manual',
  'mode.menu': 'Mode options',
  'mode.mode': 'Mode',
  'mode.toggle': 'Switch mode',

  'theme.color': 'Color',
  'theme.dark': 'Dark',
  'theme.light': 'Light',
  'theme.menu': 'Theme mode',
  'theme.system': 'System',
  'theme.toggle': 'Toggle theme',

  'tiered.form.market.cn': 'A-shares',
  'tiered.form.market.hk': 'Hong Kong',
  'tiered.form.market.jp': 'Japan',
  'tiered.form.market.kr': 'Korea',
  'tiered.form.market.tw': 'Taiwan',
  'tiered.form.market.us': 'US',

  'tiered.queued':
    'Waiting for a free slot. The server runs only a few analyses at a time; this one starts by itself when its turn comes — no need to press Start again.',
  'tiered.running': 'Running (2-5 min: fetching data, searching news, AI synthesis)…',
  'tiered.error.title': 'Analysis failed',
  'tiered.score': 'Score',
  'tiered.levels.entry': 'Entry',
  'tiered.levels.stopLoss': 'Stop loss',
  'tiered.levels.target': 'Target',
  'tiered.dataReport.technicals': 'Technicals',
  'tiered.dataReport.fundamentals': 'Fundamentals',
  'tiered.dataReport.macro_economy': 'Macro economy',
  'tiered.dataReport.positioning': 'Positioning',
  'tiered.dataReport.company_news': 'Company news',
  'tiered.dataReport.world_news': 'World news',
  'tiered.warnings': 'Warnings',
  // The warnings modal's fixed keyword list (2026-07-24): every note
  // leads with one of these, picked per rule in altWarningText.ts —
  // never AI-generated. The reward-ratio note reuses the plan-warnings
  // keyword 'tiered.warnKey.reward_below_goal'.
  'tiered.warning.key.missingData': 'Missing data',
  'tiered.warning.key.fetchFailed': 'Failed fetch',
  'tiered.warning.key.citations': 'Invalid citation',
  'tiered.warning.key.aiReply': 'Unusable LLM reply',
  'tiered.warning.key.levels': 'Price level problem',
  'tiered.warning.key.outlook': 'No outlook',
  'tiered.warning.key.vote': 'Vote problem',
  'tiered.warning.key.deepAnalysis': 'No usable vote items',
  'tiered.warning.key.riskCheck': 'Unfinished plan review',
  'tiered.warning.key.settings': 'Invalid setting',
  'tiered.warning.key.newsCap': 'Trimmed news',
  // The fallback keyword when no rule matches — every user-facing
  // "data note" reads "warning" (owner request 2026-08-25).
  'tiered.warning.key.other': 'Unknown problem',
  'tiered.summaryGroup': 'Summary',
  // Audit 2026-08-08: plain-English wording for notes that used to reach
  // the screen as raw backend text (exception reprs, variable names).
  'tiered.warning.barsLoadFailed':
    'The daily price history could not be loaded, so none of the technical numbers could be worked out.',
  'tiered.warning.yahooSummaryFailed':
    'The Yahoo Finance summary page failed to load, so the fields it feeds are blank.',
  'tiered.warning.holdersFailed':
    'The list of large fund holders failed to load, so the top-10 concentration figure and its as-of date are blank.',
  'tiered.warning.insiderFetchFailed':
    'The insider buy-and-sell filings failed to load, so the insider-trading rows are blank.',
  'tiered.warning.optionsFetchFailed':
    'The options data failed to load, so the options rows are blank.',
  'tiered.warning.earningsDateFailed':
    'The lookup for the next quarterly-report date failed, so anything depending on that date is blank.',
  'tiered.warning.earningsHistoryFailed':
    'The record of past quarterly reports failed to load, so the beat count and past report-day moves are blank.',
  'tiered.warning.reactionBarsFailed':
    'The price history needed to measure how the stock moved on past report days failed to load, so those rows are blank.',
  'tiered.warning.epsTrendFailed':
    'The history of analyst earnings estimates failed to load, so the 30-day estimate-change row is blank.',
  'tiered.warning.epsRevisionsFailed':
    'The analyst revision counts failed to load, so the 30-day increased/decreased analyst rows are blank.',
  'tiered.warning.releaseCalendarFailed':
    'The publication calendar for {label} failed to load, so its next release date is blank.',
  'tiered.warning.benchmarkBarsFailed':
    'The market index’s price history failed to load, so this stock could not be compared against the market.',
  'tiered.warning.newsHeadlinesFailed':
    'Company news could not be fetched, so this report has no headlines. The news source said: {detail}',
  'tiered.warning.sectorBarsFailed':
    'The price history for the sector fund ({ticker}) failed to load, so the sector-comparison rows are blank.',
  'tiered.warning.providerCrashed':
    'The {dataReport} data collector hit an unexpected error, so that whole section is missing from this run.',
  'tiered.warning.deepAnalysisCallFailed':
    'The LLM call for the deep analysis failed, so this run has no outlook.',
  'tiered.warning.planReviewCallFailed':
    'The LLM call for the plan review failed, so the computed plan stands as it is.',
  'tiered.warning.planReviewSkipped':
    'The plan review needs an AI key that is not configured, so the computed plan stands as it is.',
  'tiered.warning.insufficientHistory':
    'This stock has only {bars} days of price history — fewer than the {min} days the indicators need — so the technical read was skipped.',
  'tiered.warning.shortDailyHistory':
    'Only {bars} days of price history were available (a full year is about {year} trading days), so the one-year high, low and range describe the history that exists, not a full year.',
  'tiered.warning.shortWeeklyHistory':
    'Only {bars} weeks of price history were available (the weekly read wants {target}), so the weekly trend is not reliable.',
  'tiered.warning.benchmarkNotConfigured':
    'No market index is set up for this market, so the stock could not be compared against the market.',
  'tiered.warning.benchmarkShort':
    'The market index has only {bars} days of history — too little to judge the market trend or compare returns.',
  'tiered.warning.benchmarkShortRegime':
    'The market index does not have the 200 days of history the market-trend read needs.',
  'tiered.warning.noImpliedVol':
    'The options exchange published no 30-day expected-swing figure, so the implied-volatility row is blank.',
  'tiered.warning.noOptionsStockPrice':
    'The options exchange published no stock price, so the expected report-day move could not be worked out.',
  'tiered.warning.reportDateUnknown':
    'The date of the next quarterly report is unknown, so the expected report-day move could not be worked out.',
  'tiered.warning.reportDateUnreadable':
    'The next quarterly report date came back in a form the system could not read, so the expected report-day move could not be worked out.',
  'tiered.warning.reportTooFarExact':
    'The next quarterly report is {days} days away — more than {max}. Option prices that far out mostly price ordinary day-to-day movement rather than the report, so no report-day move is shown.',
  'tiered.warning.ratioMissingIngredient':
    'The ratio needs {field}, which is blank this run.',
  'tiered.warningF.daysUntilReport': 'Days until next quarterly report',
  'tiered.warning.noAtmQuotes':
    'There were no usable buy/sell quotes on the first options contract expiring after the report, so the expected report-day move could not be worked out.',
  'tiered.warning.noPostReportExpiry':
    'None of the options expiry dates that were loaded falls after the next report, so the expected report-day move could not be worked out.',
  'tiered.warning.noListedOptions':
    'This stock has no listed options, so there are no options rows to show.',
  'tiered.warning.noShortInterest':
    'Yahoo Finance published no short-selling figures for this stock, so the short-interest rows are blank.',
  'tiered.warning.noOwnership':
    'Yahoo Finance published no ownership figures for this stock, so the ownership rows are blank.',
  'tiered.warning.noEarningsHistory':
    'No records of past quarterly reports came back for this stock, so the beat count and past report-day move rows are blank.',
  'tiered.warning.tooFewReports':
    'Only {count} past reports fall inside the loaded price history — too few to average how the stock moves on report day.',
  'tiered.warning.fredKeyMissing':
    'The economy-data service (FRED) has no access key configured, so no economy numbers could be loaded.',
  'tiered.warning.noReleaseDate':
    'No future release date for {label} has been published yet.',
  'tiered.warning.fomcTableExhausted':
    'The built-in list of Federal Reserve interest-rate meeting dates has run past its last entry, so the next rate-decision date is blank.',
  'tiered.warning.sectorUnknown':
    'This company’s sector (its industry family) is unknown, so the sector-comparison rows are blank.',
  'tiered.warning.sectorNoEtf':
    'This company’s sector has no matching sector fund set up yet (US sectors only for now), so the sector-comparison rows are blank.',
  'tiered.warning.sectorNeedsBenchmark':
    'The sector comparison is measured against the market’s return, and that is missing, so the sector rows are blank.',
  'tiered.warning.sectorShort':
    'The sector fund ({ticker}) has only {bars} days of history — too little to compare returns — so the sector rows are blank.',
  'tiered.warning.noClosePrice':
    'No closing price was available, so no trade plan could be worked out.',
  'tiered.warning.noEntryAnchor':
    'None of the prices the entry anchors to — the 50-day average, the 200-day average, or the nearest support level — were available, so no trade plan could be worked out.',
  'tiered.warning.noTechnicalsForLevels':
    'The technical data is missing, so no trade plan could be worked out.',
  'tiered.warning.duplicateAdjust':
    'The AI proposed two changes to the {level}; the first was kept and the second ignored.',
  'tiered.warning.planAdjustDropped':
    'The AI’s proposed change to the {level} could not back its numbers with anything in the report, so the change was dropped.',
  'tiered.warning.planReplyProblem':
    'The AI’s plan-review reply contained something the system could not use, so that part was ignored.',
  'tiered.warning.planNoConverge':
    'Every change the AI proposed still tripped a risk check, so all of them were discarded and the plain computed plan stands.',
  'tiered.warning.noGradableFields':
    'No report fields were available for the listers to grade, so this run has no outlook.',
  'tiered.warning.noEvidenceToVote':
    'No report data reached the listers, so there was nothing to judge. Re-run this stock.',
  'tiered.warning.rewardRiskDefaulted':
    'The reward ratio must be above 1. The value given was ignored and the default was used instead.',
  'tiered.warning.adjustUnknownLevel':
    'The AI proposed a change to something that is not one of the plan’s levels, so it was ignored.',
  'tiered.warning.downtrend':
    'The close is at or below its 50-day average — a pullback buy against the trend carries extra downside risk.',
  'tiered.warning.trendCheckSkipped': 'The 50-day average was unavailable, so the trend check was skipped.',
  'tiered.warning.summaryLinksDropped':
    'Some summary citations failed the code checks even after fixes — those values still show, but without links.',
  'tiered.warning.optionsOiMissing':
    'Options open interest came back missing or zero at the source — the put/call OI ratio and total are left blank rather than showing a misleading 0.',
  'tiered.warning.optionsVolumeMissing':
    'Options volume came back missing or zero at the source — the put/call volume ratio is left blank rather than showing a misleading 0.',
  'tiered.warning.insiderRowsMissing':
    'Yahoo returned no insider transaction rows at all — that is indistinguishable from a data outage, so the insider block is left blank instead of claiming zero activity.',
  // News-screen stage degradations (judge/group/rank/summarize) — every
  // failure lowers the card's polish, never drops news.
  'tiered.warning.newsJudgeFailed':
    'The LLM reply that rates each news article’s relevance and importance was missing or unreadable, so every article was kept unrated.',
  'tiered.warning.newsJudgeMissing':
    'The AI’s news-rating reply skipped {count} article(s) — those were kept unrated.',
  'tiered.warning.newsGroupFailed':
    'The LLM reply that merges articles covering the same story was missing or unreadable, so no merging was done — the same story may appear more than once.',
  'tiered.warning.newsGroupPartial':
    'The AI’s story-merging reply skipped {count} article(s) — those stay as separate items.',
  'tiered.warning.newsRankFailed':
    'The LLM reply that orders events by importance was missing or unreadable, so events are shown in importance-score order instead.',
  'tiered.warning.newsRankPartial':
    'The AI’s ranking reply skipped {count} event(s) — those were placed last, in importance-score order.',
  'tiered.warning.newsSummaryFailed':
    'The LLM reply that writes the one-sentence summaries was missing or unreadable, so the news feed’s own wording is shown instead.',
  'tiered.warning.newsSummaryMissing':
    'The AI’s summary reply skipped {count} article(s) — those show the news feed’s own wording.',
  'tiered.warning.newsTrimmed':
    'Busy news window: more events qualified than the card can show — the {count} ranked below the top {max} were left off.',
  'tiered.group.trend': 'Price & trend',
  'tiered.group.momentum': 'Momentum',
  'tiered.group.volatility': 'Volatility & range',
  'tiered.group.structure': 'Price structure',
  'tiered.group.volume': 'Volume',
  'tiered.group.meta': 'Data & score',
  'tiered.group.reportInfo': 'Report info',
  'tiered.group.earnings': 'Earnings',
  'tiered.group.other': 'Other',
  'tiered.warning.fetchFailed': 'One news article ({domain}) couldn’t be downloaded, so it wasn’t used.',
  'tiered.warning.fundamentalsUnavailable':
    'Official U.S. filings data (SEC) couldn’t be loaded, so some fundamentals figures may be missing.',
  'tiered.warning.valuationUnavailable': 'Valuation ratios from Yahoo Finance couldn’t be loaded.',
  'tiered.warning.macroUnavailable':
    'One economic indicator ({series}) couldn’t be loaded from the FRED database.',
  'tiered.warning.indicatorNoHistory':
    'There was not enough price history to compute this value.',
  'tiered.warning.macroFieldMissing':
    'The data source did not return enough data to compute this value.',
  'tiered.warning.adjustmentRejected':
    'The AI wanted to tweak the {level}, but its suggestion broke the rules, so the formula’s number was kept.',
  'tiered.warning.stopFallback':
    'The formula’s stop-loss price wasn’t usable, so a volatility-based (ATR) stop was used instead.',
  'tiered.warning.noAtrStop': 'No volatility data (ATR) was available, so no stop-loss price could be computed.',
  'tiered.warning.noAtrStopTarget':
    'No volatility data (ATR) was available, so neither the stop-loss nor the target price could be computed.',
  'tiered.warning.noEntryNoStop': 'There is no usable entry price, so no stop-loss could be set.',
  'tiered.warning.summaryFailed':
    'The deep analysis’s written summary couldn’t be produced — the computed outlook is unaffected.',
  'tiered.warning.badSetting': 'One sizing setting isn’t a number and was ignored.',
  'tiered.help.entry':
    'Ideal buy price.\nUsually near a support level — a price where buyers stepped in before.',
  'tiered.help.stopLoss':
    'Safety exit.\nA fall to here means the idea was wrong — selling caps the loss.',
  'tiered.help.target': 'Profit target.\nWhere the analysis suggests selling to lock in gains.',
  'tiered.empty': 'Enter a ticker to start a tiered analysis.',
  'tiered.history.title': 'Run history',
  'tiered.status.queued': 'Queued',
  'tiered.status.queuedAt': 'Queued ({position})',
  'tiered.status.running': 'Running',
  'tiered.status.done': 'Done',
  'tiered.status.failed': 'Failed',
  'tiered.help.tier':
    'Tier 1 (preliminary analysis): the six data reports plus one LLM call that gives the outlook.\nTier 2 (deep analysis): skips that single call — two LLM listers grade every report field into vote items, and every vote item is voted on instead. Slower, more thorough.\n(Tier 3 is retired.)',
  'tiered.llmUsage': 'This run used {calls} LLM calls ({tokens} tokens)',
  'tiered.help.llmUsage':
    'LLM calls this run made (each one is a request to the language-model API), and their total tokens (the billing unit).\nClick to see every call’s input and output.',
  'tiered.transcript.call': 'LLM call {n}',
  'tiered.transcript.for': 'for',
  'tiered.transcript.llm': 'llm',
  'tiered.transcript.time': 'time',
  'tiered.transcript.tokenCount': '{n} tokens',
  'tiered.transcript.loading': 'Loading…',
  'tiered.transcript.error': 'Could not load the transcript: {error}',
  'tiered.transcript.empty': 'This run’s transcript has expired (kept 14 days).',
  'tiered.transcript.input': 'input',
  'tiered.transcript.output': 'output',
  'tiered.transcript.failed': 'Call failed: {error}',
  'tiered.transcript.noReply': '(no reply)',
  'tiered.transcript.callLoading': 'Loading…',
  'tiered.transcript.callError': 'Could not load this call: {error}',
  'tiered.kind.formula': 'formula',
  'tiered.kind.adjustment': 'adjustment',
  'tiered.kind.whyBlank': 'why blank',
  'tiered.kind.warnings': 'warnings',
  'tiered.blankFallback':
    'This field has no value in this run — the data needed to compute it was unavailable.',
  'tiered.levelModal.noBase':
    'This run lacked the data needed to compute this level, so there is no formula base.',
  'tiered.levelModal.references': 'References',
  'tiered.help.deepAnalysis':
    'Two LLM listers independently grade every field of the six data reports (technicals, fundamentals, positioning, macro economy, company news, world news) as bullish, bearish or neutral; each bullish or bearish grade becomes a one-sentence vote item with a 1-5 score.\nCode verifies every cited value: it must match the report’s displayed number exactly and appear in the sentence; failed citations go back to the lister to fix (up to 3 times), and vote items still broken are crossed out and dropped.\nCode merges the two sheets, and each vote item lives or dies by majority vote (at most 3 votes): its lister counts as one valid vote, so a field both listers graded the same way is confirmed on the spot; a checker casts the second vote on single-lister vote items; a deciding vote breaks 1-1 ties.\nCode sums the surviving bullish vs bearish vote items by their scores into the outlook score — no LLM touches the numbers. A last LLM call writes the summary from the voted list; the score never depends on it.',
  'tiered.deepAnalysis.noOutlook':
    'The deep analysis produced no outlook — re-run the stock (see Warnings).',
  'tiered.tree.bullish': 'bullish',
  'tiered.tree.bearish': 'bearish',
  'tiered.tree.valid': 'valid',
  'tiered.tree.invalid': 'invalid',
  'tiered.tree.scores': 'Scores',
  'tiered.tree.finalScore': 'final outlook score',
  'tiered.tree.title': 'Vote items',
  'tiered.tree.loading': 'Loading the vote items…',
  'tiered.tree.loadError': 'Could not load the vote items: {error}',
  'tiered.tree.howItWorks': 'How this works',
  'tiered.tree.explain1':
    'Two LLM listers each independently grade every field of the six data reports (technicals, fundamentals, positioning, macro economy, company news, world news) as bullish, bearish or neutral. Neither sees the other’s work.',
  'tiered.tree.explain2':
    'A bullish or bearish grade becomes a one-sentence vote item that quotes the field’s value; a neutral grade produces nothing. Every lister or checker that handles a vote item also gives it a score from 1 to 5 (1 = very minor, 5 = very important) and a reason.',
  'tiered.tree.explain3':
    'Code verifies every number a vote item cites against the reports; failed citations go back to the lister to fix (up to 3 times), and a vote item still broken is crossed out and counts toward nothing.',
  'tiered.tree.explain4':
    'Code merges the two grade sheets. A field both listers graded the same way becomes one vote item with two listers — already agreed 2-0, so it carries no check marks.',
  'tiered.tree.explain5':
    'A vote item only one lister listed (or a field the two graded opposite ways) is checked by a checker — the ✓ or ✗ after it; click the mark to read the reasoning.',
  'tiered.tree.explain6':
    'If that check says invalid, the vote item is tied 1-1 and one more LLM call casts the deciding vote — the second mark. A tie with no deciding vote is left out of the score.',
  'tiered.tree.explain7':
    'A vote item with two ✗ loses the vote and is crossed out; everything not crossed out counts, with a score equal to the median of all its 1-5 scores. Click a score to read why.',
  'tiered.tree.explain8':
    'Code computes the final outlook score: 10 × the bullish vote items’ score sum ÷ all counted vote items’ score sum. Below 4 bearish, 4–6 neutral, above 6 bullish. No LLM writes it.',
  'tiered.tree.explain9':
    'A last LLM call writes the summary from the voted list; its numbers are citation-checked the same way, and if it fails the computed score still stands.',
  'tiered.tree.codeCheck': 'code check result',
  'tiered.warning.listerDegradedRole':
    '{role} — the grade sheet kept coming back invalid; this run used the other lister’s sheet only.',
  'tiered.warning.sheetsVoided':
    'Both listers kept returning invalid grade sheets — the deep analysis was voided.',
  'tiered.warning.noOutlook':
    'The deep analysis produced no outlook — re-run the stock.',
  'tiered.warning.preliminaryNoOutlook':
    'The preliminary analysis produced no outlook — re-run the stock.',
  'tiered.warning.preliminaryCallFailed':
    'The LLM call for the preliminary analysis failed, so this run has no outlook.',
  'tiered.warning.preliminaryReplyRejected':
    'The preliminary analysis’s reply was unusable ({problem}), so it was asked again.',
  'tiered.warning.checkDegraded':
    'The check round kept coming back invalid — vote items were counted on their lister’s vote alone.',
  'tiered.warning.tiebreakDegraded':
    'The deciding round kept coming back invalid — tied vote items were treated as unresolved and left out of the score.',
  'tiered.warning.voteDiscarded':
    'A vote’s citations still failed the code check after the fix attempts — that vote was discarded.',
  'tiered.warning.unresolved':
    'A vote item was tied 1-1 with no deciding vote — it was treated as unresolved and left out of the score.',
  'tiered.warning.allConfirmed':
    'Every vote item was listed independently by both listers — no check votes were needed.',
  'tiered.warning.struckBullet':
    'A vote item’s citations still failed the code check after 3 fix attempts — it is crossed out and counts toward nothing.',
  'tiered.warning.fixRoundLost': 'A citation-fix reply was unreadable — that fix round was lost.',
  'tiered.warning.stageRetriedRole':
    '{role} — the first reply was invalid; the retry succeeded.',
  'tiered.warning.stageInvalidRole':
    '{role} — the reply was still invalid after a retry.',
  'tiered.role.checkRound': 'Check vote',
  'tiered.role.decidingRound': 'Deciding vote',
  'tiered.role.reportOutline': 'Report writer',
  'tiered.role.newsJudge': 'News relevance judge',
  'tiered.role.newsGrouping': 'Same-story news grouping',
  'tiered.role.newsRanking': 'News importance ranking',
  'tiered.role.newsSummary': 'News summary writer',
  'tiered.role.preliminaryAnalysis': 'Preliminary analysis',
  'tiered.role.planReview': 'Plan review',
  'tiered.role.citationFix': '{role} (citation fix)',
  'tiered.warning.stageWrongLanguageRetried':
    '{role} — the first reply was not in {language}; asking again fixed it.',
  'tiered.warning.stageWrongLanguageKept':
    '{role} — the reply was still not in {language} after asking again {retries} times, so it is shown as written.',
  'tiered.languageName.en': 'English',
  'tiered.languageName.zh': 'Simplified Chinese',
  'tiered.warning.emptyLedger': 'No vote items survived to count, so the final score defaults to neutral 5.',
  'tiered.warning.thinBase':
    'Most of the listers’ initial vote items did not survive — the score rests on a thin base.',
  'tiered.help.deepAnalysisScore':
    'The deep analysis’s final outlook score, out of 10, at two decimals.\n0 = strongly bearish, 5 = neutral, 10 = strongly bullish.\nBelow 4 bearish, 4–6 neutral, above 6 bullish.\nPure code: 10 × the bullish vote items’ score sum ÷ all vote items’ score sum, over only the vote items that survived checking. See Scores at the bottom of Vote items.',
  'tiered.help.sizing':
    'Fixed arithmetic, no AI.\nEvery number links to where it appears in this report.\nThe result is rounded down to whole shares, and one stock may use at most 25% of capital.',
  'tiered.form.ticker': 'Ticker',
  'tiered.form.tier': 'Tier',
  'tiered.form.capital': 'Capital',
  'tiered.form.capitalCurrency': 'Capital: {currency}',
  'tiered.form.risk': 'Risk: %',
  'tiered.form.title': 'New run',
  'tiered.form.start': 'Start',
  'tiered.form.noticeTitle': 'Heads up',
  'tiered.form.needTickerFirst':
    'Pick a ticker first — capital is in the currency of the ticker’s market.',
  'tiered.form.errorTitle': 'Error',
  'tiered.form.missingIntro': 'These required fields are not filled in:',
  'tiered.form.duplicateRunning':
    'An identical {ticker} run is already running (same capital, risk, reward ratio, max hold and tier). It is expanded in the run history below. Wait for it to finish, or change one of the inputs.',
  'tiered.form.duplicateQueued':
    'An identical {ticker} run is already waiting in the queue (same capital, risk, reward ratio, max hold and tier). It is expanded in the run history below and starts by itself. Wait for it, or change one of the inputs.',
  'tiered.form.req.ticker': 'Ticker',
  'tiered.form.req.tier': 'Tier',
  'tiered.form.req.capital': 'Capital',
  'tiered.form.req.risk': 'Risk',
  'tiered.form.req.reward': 'Reward ratio',
  'tiered.form.req.hold': 'Max hold',
  'tiered.form.tierOption1': '1: preliminary analysis',
  'tiered.form.tierOption2': '2: deep analysis',
  'tiered.form.tickerPh': 'Enter ticker...',
  'tiered.form.tierPh': 'Enter tier...',
  'tiered.form.capitalPh': 'Enter capital...',
  'tiered.form.riskPh': 'Enter risk...',
  'tiered.form.reward': 'Reward ratio: x',
  'tiered.form.rewardPh': 'Enter ratio...',
  'tiered.form.lowRewardWarn':
    'A reward ratio below 1.5 means the trade barely pays for its risk — 1.5× is the common minimum. The run will still use your {value}× target.',
  'tiered.help.reward':
    'The reward ratio you ask the plan for (how many times the accepted risk the potential profit should be). Required; the default is 2.\nTarget = entry + ratio × risk. If overhead resistance caps the target below your ratio, the plan carries a warning (below the 1.5 hard floor, no plan is issued at all).',
  'tiered.form.hold': 'Max hold: weeks',
  'tiered.form.holdPh': 'Enter max hold...',
  'tiered.help.hold':
    'The longest you plan to hold the trade. Required; the default is 2 weeks.\nThe same number goes to the AI (to judge which evidence matters at this timescale), onto the report, and into the forward test as the grading window — the AI, you and the testing stay on one page.',
  'tiered.form.marketOpenTitle': 'Market is open',
  'tiered.form.marketOpenTrading':
    'The {market} market is trading right now. This app only analyzes completed trading days, so today has no data to analyze yet.',
  'tiered.form.marketOpenHours':
    'Today’s session: {open}–{close} market local time, which is {openLocal}–{closeLocal} on your clock.',
  'tiered.form.marketOpenMixedData':
    '“Run anyway” analyzes the previous completed trading day: the technicals report will only use data up to that day’s close, but news and other sources may be live — so the report can mix data from two different points in time.',
  'tiered.form.marketOpenBestWindow':
    'Also, even after the close, data sources can lag live data by up to 30 minutes, and a run itself takes a while — so the best time to use the app is from 30 minutes after the close until 30 minutes before the next open.',
  'tiered.form.runAnyway': 'Run anyway',
  'tiered.pill.ticker': 'Ticker: {value}',
  'tiered.pill.tier': 'Tier: {value}',
  'tiered.pill.capital': 'Capital: {value} {currency}',
  'tiered.pill.risk': 'Risk: {value}%',
  'tiered.pill.reward': 'Reward ratio: {value}×',
  'tiered.pill.hold': 'Max hold: {value}w',
  'tiered.pill.capitalMin': 'Capital Min: {value}',
  'tiered.pill.capitalMax': 'Capital Max: {value}',
  'tiered.pill.riskPctMin': 'Risk Min: {value}%',
  'tiered.pill.riskPctMax': 'Risk Max: {value}%',
  'tiered.pill.dateMin': 'Date Min: {value}',
  'tiered.pill.dateMax': 'Date Max: {value}',
  'tiered.pill.rewardRatioMin': 'Reward ratio Min: {value}×',
  'tiered.pill.rewardRatioMax': 'Reward ratio Max: {value}×',
  'tiered.filter.tickerPh': 'Enter ticker...',
  'tiered.filter.capital': 'Capital',
  'tiered.filter.risk': 'Risk: %',
  'tiered.filter.date': 'Date: yyyy/mm/dd',
  'tiered.filter.tier': 'Tier',
  'tiered.filter.tierPh': 'Enter tier...',
  'tiered.filter.holdPh': 'Enter max hold...',
  'tiered.filter.reward': 'Reward ratio: ×',
  'tiered.filter.min': 'Min',
  'tiered.filter.max': 'Max',
  'tiered.history.shares': '{value} shares',
  'tiered.history.tier': 'Tier {value}',
  'tiered.history.hold': '{value}w',
  // The run list's column-name header row.
  'tiered.history.h.ticker': 'Ticker',
  'tiered.history.h.capital': 'Capital',
  'tiered.history.h.risk': 'Risk',
  'tiered.history.h.reward': 'Reward ratio',
  'tiered.history.h.hold': 'Max hold',
  'tiered.history.h.tier': 'Tier',
  'tiered.history.h.status': 'Status',
  'tiered.history.h.outlook': 'Outlook',
  'tiered.history.h.date': 'Date',
  'tiered.history.first': 'First page',
  'tiered.history.prev': 'Previous page',
  'tiered.history.next': 'Next page',
  'tiered.history.last': 'Last page',
  'tiered.history.none': 'No runs match these filters',
  'tiered.history.loading': 'Loading report…',
  'tiered.history.delete': 'Delete this run',
  'tiered.history.cancel': 'Cancel this run',
  'tiered.history.deleteAsk': 'Delete this run and its LLM transcript? This cannot be undone.',
  'tiered.history.cancelAsk': 'Take this run out of the line? It will not start.',
  'tiered.history.confirmDelete': 'Delete',
  'tiered.history.confirmCancel': 'Cancel run',
  'tiered.history.keep': 'Keep',
  'tiered.history.deleting': 'Deleting…',
  'tiered.history.deleteInProgress': 'This run is in progress and cannot be removed. Wait for it to finish, then delete it.',
  'tiered.history.deleteError': 'Could not delete: {error}',
  'tiered.dataReports.title': 'Data reports',
  'tiered.eventsNone': 'None in the last {count} days',
  'tiered.eventsNoneGeneric': 'None found',
  'tiered.eventsWindow': 'last {count} days',
  'tiered.deepAnalysis.title': 'Deep analysis',
  'tiered.rewardBelowGoal':
    'This plan’s reward ratio is {ratio}, below your {goal}× goal — overhead resistance caps the target.',
  'tiered.roundLevelTitle': 'Round level',
  'tiered.roundLevelBody':
    '{value} is the nearest round price below the current price. It comes from no data row — the code computes it on the spot: crowd orders cluster at round numbers, forming a weak support.',
  'tiered.f.capital': 'capital',
  'tiered.f.risk': 'risk per trade',
  'tiered.f.entry': 'entry',
  'tiered.f.stop': 'stop loss',
  'tiered.sources': 'Sources',
  'tiered.levels.computed': 'Computed',
  'tiered.levels.adjusted': 'Adjusted',
  'tiered.levels.keep': 'keep',
  'tiered.levels.shares': 'Shares',
  'tiered.levels.warnings': 'Warnings',
  'tiered.warn.none': 'none',
  'tiered.warn.downtrend':
    'The close ({close}) is at or below its 60-day average ({sma60}) — the stock is in a medium-term downtrend, so entering here is buying against the trend and carries extra risk of further downside.',
  'tiered.warn.downtrend_50':
    'The close ({close}) is at or below its 50-day average ({sma50}) — the stock is in a medium-term downtrend, so entering here is buying against the trend and carries extra risk of further downside.',
  'tiered.warn.earnings_soon':
    'The next earnings report is {days} day(s) away ({date}) — inside a typical swing hold. Technicals do not survive earnings: one announcement can gap the price past any stop. Plan to exit before the report, or size for the gap.',
  'tiered.warn.macro_event_soon':
    'The {event} is {days} day(s) away ({date}) — inside a typical swing hold. This is market-wide gap risk: one number can move every stock at once. Plan smaller size around it, or size the stop for the gap.',
  'tiered.warnEvent.rate_decision': 'next official interest rate decision',
  'tiered.warnEvent.inflation_data': 'next inflation data release',
  'tiered.warnEvent.employment_data': 'next employment data release',
  'tiered.warn.gap_atr':
    'If overnight news gaps the open 1 ATR ({atr}) below your stop ({stop}), it opens at {atrOpen}; the stop order sells there — a {atrLoss} loss, {atrExtra} more than the {planned} you planned.',
  'tiered.warn.gap_worst':
    'If the stock repeats its worst day of the past year ({worstDayPct}%), the open lands at {worstOpen}, past your stop ({stop}) — selling there loses {worstLoss}, {worstExtra} more than the {planned} you planned.',
  // Names of the warning popup's computed values (also the variable
  // names in their formula word-lines).
  'tiered.warnF.gapOpen': 'gapped open',
  'tiered.warnF.gapLoss': 'gap loss',
  'tiered.warnF.plannedLoss': 'planned loss',
  'tiered.warnF.worstOpen': 'worst-day open',
  'tiered.warnF.worstLoss': 'worst-day loss',
  'tiered.warnF.ratio': 'reward ratio',
  'tiered.f.shares': 'shares',
  'tiered.f.target': 'target',
  // The fixed keyword each risk line opens with (code-picked from the
  // check id, never AI-written).
  'tiered.warnKey.downtrend': 'Downtrend',
  'tiered.warnKey.earnings_soon': 'Earnings soon',
  'tiered.warnKey.macro_event_soon': 'Macro event soon',
  'tiered.warnKey.gap_atr': 'Overnight gap risk',
  'tiered.warnKey.gap_worst': 'Worst-day gap risk',
  'tiered.warnKey.reward_below_goal': 'Low reward ratio',
  'tiered.checkKey.downtrend': 'Downtrend',
  'tiered.checkKey.liquidity': 'Liquidity',
  'tiered.checkKey.volatility': 'Volatility',
  'tiered.checkKey.stop_vs_support': 'Support',
  'tiered.reviewFail.title': 'Why the plan keeps its computed numbers',
  'tiered.reviewFail.intro':
    'The AI tried adjusting this plan, but every attempt still tripped a risk check, so all adjustments were discarded and the formula-computed plan stands.',
  'tiered.reviewFail.round': 'Round {round} still flagged: {checks}',
  'tiered.help.capital':
    'The money you trade with, in the ticker’s own currency.\nThe shares computation starts from it.\nRemembered for your next run.',
  'tiered.help.riskPct':
    'The most you accept losing on one trade, as a percent of capital.\n1–2% is common.',

  // ---- Outlook redesign ----
  'tiered.preliminaryAnalysis.title': 'Preliminary analysis',
  'tiered.outlook': 'Outlook',
  'tiered.action': 'Action',
  'tiered.actionRatio': 'current reward ratio is {ratio}',
  'tiered.outlook.bullish': 'Bullish',
  'tiered.outlook.neutral': 'Neutral',
  'tiered.outlook.bearish': 'Bearish',
  'tiered.outlook.no_outlook': 'No outlook',
  'tiered.action.buy_now': 'Buy now',
  'tiered.action.buy_later': 'Buy later',
  'tiered.action.no_trade': 'No trade',
  'tiered.action.unknown': 'Re-run — this run produced no usable outlook',
  'tiered.help.outlook':
    'The outlook is the judgment on the stock itself (bullish / neutral / bearish), regardless of whether you hold it.\nThe action is derived by code from the outlook: bullish → buy now (the trade plan’s reward ratio meets your goal) or buy later (it falls short); neutral or bearish → no trade.',
  'tiered.help.action':
    'Your personal instruction, derived by fixed code rules from the outlook.\nBullish splits in two: the trade plan’s actual reward ratio reaches the goal you set → “Buy now”; it falls short (e.g. overhead resistance caps the target) → “Buy later” (wait for a better price before entering).',
  'tiered.staleWarning':
    'This report is from a previous trading day — re-run for a fresh plan.',
  'tiered.tradePlan.title': 'Trade plan',
  'tiered.help.plan':
    'The plan levels a fixed formula computed from the price data (no LLM).\nWhat shows depends on the Action: buy now or buy later → the full levels table; no trade → no levels.',
  'tiered.filter.status': 'Status',
  'tiered.filter.statusPh': 'Enter status...',
  'tiered.pill.status': 'Status: {value}',
  'tiered.filter.outlook': 'Outlook',
  'tiered.filter.outlookPh': 'Enter outlook...',
  'tiered.pill.outlook': 'Outlook: {value}',

  'tiered.tree.bullishScoreSum': 'bullish score sum',
  'tiered.tree.totalScoreSum': 'total score sum',

  // ---- Tier-2 details (v11: 1-5 scores + score reasons) ----
  'tiered.tree.lister': 'Lister {n}',
  'tiered.tree.checker': 'Checker {n}',
  'tiered.tree.validityLine': 'result: {value}',
  'tiered.tree.reasonPrefix': 'reason:',
  'tiered.tree.scoreLine': 'score: {value}',
  'tiered.tree.scoresList': 'Scores: {value}',
  'tiered.tree.medianTitle': 'Score',
  'tiered.tree.medianLine': 'Median: {value}',

  // Chat page (2026-09-21): the bot reads and acts through the app's own API.
  'chat.sidebar.title': 'History',
  'chat.new': 'New chat',
  'chat.facts.inputs': 'user inputs',
  'chat.facts.tokens': 'total tokens',
  'chat.facts.start': 'start date',
  'chat.facts.end': 'end date',
  'chat.sidebar.delete': 'Delete this conversation',
  'chat.sidebar.deleteAsk': 'Delete this conversation? This cannot be undone.',
  'chat.sidebar.confirmDelete': 'Delete',
  'chat.sidebar.keep': 'Keep',
  'chat.empty.hint':
    'This ReAct agent is powered by your main LLM. It has a general understanding of this app and access to all APIs available to the user. Note that it does NOT have access to the source code.',
  'chat.composer.placeholder': 'Enter = send; Shift+Enter = new line',
  'chat.composer.send': 'Send',
  'chat.composer.waitConfirm': 'Answer the question above first.',
  'chat.step.tool': 'Step {n}: LLM decided to call a tool',
  'chat.step.say': 'Step {n}: LLM decided to say something',
  'chat.step.failed': 'Step {n}: LLM call failed',
  'chat.step.toolCall': 'Step {n}: tool call',
  'chat.tool.name': 'name',
  'chat.tool.decision': 'decision',
  'chat.tool.approve': 'approve',
  'chat.tool.decline': 'decline',
  'chat.tool.status': 'status',
  'chat.tool.status.waiting': 'waiting',
  'chat.tool.status.processing': 'processing',
  'chat.tool.status.done': 'done',
  'chat.tool.status.failed': 'failed',
  'chat.tool.approved': 'approved',
  'chat.tool.declined': 'declined',
  'chat.tool.truncated': 'The model saw a cut-down copy.',
  'chat.tool.input': 'input',
  'chat.tool.output': 'output',
  'chat.usage': 'This step used {tokens} tokens',
  'chat.step.noUsage': 'This step did not report its tokens',
  'chat.transcript.missing': 'This reply’s transcript was not kept (replies from before 2026-09-23 have none).',
  'chat.help.usage':
    'Tokens this LLM call used (the billing unit). Every call resends the standing instructions, the tool menu and the whole conversation, so even a "hi" costs a few thousand.\nClick to see the exact prompt and reply.',
  'chat.notice.toolCallLimit': 'The bot stopped at its tool-call limit for one turn.',
  'chat.notice.wrongLanguage': 'This reply is not in the chosen language.',
  'chat.error.busy': 'The bot is still working on the previous message.',
  'chat.error.notConfigured': 'No model is configured. Set MAIN_LLM and LLM_API_KEY in .env first.',
  'chat.error.send': 'Could not send: {error}',

};

export const UI_TEXT: Record<UiLanguage, Record<UiTextKey, string>> = {
  zh,
  en,
  ko,
};

export type UiTextParams = Record<string, string | number>;

export function formatUiText(template: string, params?: UiTextParams): string {
  if (!params) {
    return template;
  }

  return template.replace(/\{(\w+)\}/g, (match, key: string) => {
    const value = params[key];
    return value === undefined ? match : String(value);
  });
}
