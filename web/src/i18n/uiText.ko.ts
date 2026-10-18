import type { UiTextKey } from './uiText';

// Korean column of the UI word table (added 2026-10-04). Same keys as
// `zh` / `en` in uiText.ts; the parity test in __tests__/uiText.test.ts
// keeps the three in step.
export const ko: Record<UiTextKey, string> = {

  'language.menu': 'UI 언어 옵션',
  'language.toggle': 'UI 언어 전환',
  'language.uiLanguage': '언어',

  // 모드 메뉴 (2026-09-26): 수동 분석 페이지, 또는 그것을 구동하는 에이전트.
  'mode.agentic': '에이전트',
  'mode.manual': '수동',
  'mode.menu': '모드 옵션',
  'mode.mode': '모드',
  'mode.toggle': '모드 전환',

  'theme.color': '색상',
  'theme.dark': '다크',
  'theme.light': '라이트',
  'theme.menu': '테마 모드',
  'theme.system': '시스템',
  'theme.toggle': '테마 전환',

  'tiered.form.market.cn': '중국 A주',
  'tiered.form.market.hk': '홍콩 주식',
  'tiered.form.market.jp': '일본 주식',
  'tiered.form.market.kr': '한국 주식',
  'tiered.form.market.tw': '대만 주식',
  'tiered.form.market.us': '미국 주식',

  'tiered.queued':
    '빈 자리를 기다리는 중입니다. 서버는 한 번에 소수의 분석만 실행하며, 차례가 오면 자동으로 시작됩니다. 시작을 다시 누를 필요가 없습니다.',
  'tiered.running': '분석 중 (약 2~5분: 데이터 수집, 뉴스 검색, AI 종합)…',
  'tiered.stopping': '중지 중… 진행 중인 단계가 먼저 끝나고, 보고서에는 완료된 부분만 표시됩니다.',
  'tiered.stoppedFinished': '{stage} 단계에서 중지했습니다. {stage} 단계는 완료되어 표시됩니다.',
  'tiered.stoppedUnfinished': '{stage} 단계에서 중지했습니다. {stage} 단계는 완료되지 않아 표시되지 않습니다.',
  'tiered.error.title': '분석 실패',
  'tiered.score': '점수',
  'tiered.levels.entry': '진입가',
  'tiered.levels.stopLoss': '손절가',
  'tiered.levels.target': '목표가',
  'tiered.dataReport.technicals': '기술적 분석',
  'tiered.dataReport.fundamentals': '펀더멘털',
  'tiered.dataReport.macro_economy': '거시경제',
  'tiered.dataReport.positioning': '포지셔닝',
  'tiered.dataReport.company_news': '기업 뉴스',
  'tiered.dataReport.world_news': '세계 뉴스',
  'tiered.warnings': '경고',
  // 경고 모달의 고정 키워드 목록 (2026-07-24): 모든 설명은 이 중 하나로
  // 시작하며 altWarningText.ts의 규칙이 고릅니다. AI가 생성하지 않습니다.
  // 손익비 설명은 계획 경고 키워드 'tiered.warnKey.reward_below_goal'을 재사용합니다.
  'tiered.warning.key.missingData': '데이터 누락',
  'tiered.warning.key.fetchFailed': '가져오기 실패',
  'tiered.warning.key.citations': '인용 무효',
  'tiered.warning.key.aiReply': 'LLM 응답 사용 불가',
  'tiered.warning.key.levels': '가격 수준 문제',
  'tiered.warning.key.outlook': '전망 없음',
  'tiered.warning.key.vote': '투표 문제',
  'tiered.warning.key.deepAnalysis': '사용 가능한 투표 항목 없음',
  'tiered.warning.key.riskCheck': '계획 검토 미완료',
  'tiered.warning.key.settings': '설정 무효',
  'tiered.warning.key.newsCap': '뉴스 잘림',
  // 규칙에 맞는 것이 없을 때의 기본 키워드. 사용자에게 보이는 모든
  // "데이터 설명"은 "경고"라고 부릅니다 (소유자 요청 2026-08-25).
  'tiered.warning.key.other': '알 수 없는 문제',
  'tiered.summaryGroup': '요약',
  // 감사 2026-08-08: 백엔드 원문(예외 표현, 변수명)이 그대로 화면에 닿던
  // 설명을 쉬운 말로 다시 씀.
  'tiered.warning.barsLoadFailed':
    '일별 가격 이력을 불러오지 못해 기술적 분석 수치를 하나도 계산할 수 없었습니다.',
  'tiered.warning.yahooSummaryFailed':
    'Yahoo Finance 요약 페이지를 불러오지 못해 해당 페이지에서 가져오는 항목이 비어 있습니다.',
  'tiered.warning.holdersFailed':
    '대형 펀드 보유자 목록을 불러오지 못해 상위 10개 집중도 수치와 기준일이 비어 있습니다.',
  'tiered.warning.insiderFetchFailed':
    '내부자 매매 공시를 불러오지 못해 내부자 거래 행이 비어 있습니다.',
  'tiered.warning.optionsFetchFailed':
    '옵션 데이터를 불러오지 못해 옵션 행이 비어 있습니다.',
  'tiered.warning.earningsDateFailed':
    '다음 분기 실적 발표일 조회에 실패해 해당 날짜에 의존하는 항목이 비어 있습니다.',
  'tiered.warning.earningsHistoryFailed':
    '과거 분기 실적 기록을 불러오지 못해 예상치 상회 횟수와 과거 실적 발표일 변동폭이 비어 있습니다.',
  'tiered.warning.reactionBarsFailed':
    '과거 실적 발표일의 주가 반응을 측정하는 데 필요한 가격 이력을 불러오지 못해 해당 행이 비어 있습니다.',
  'tiered.warning.epsTrendFailed':
    '애널리스트 이익 추정치 이력을 불러오지 못해 30일 추정치 변화 행이 비어 있습니다.',
  'tiered.warning.epsRevisionsFailed':
    '애널리스트 추정치 조정 인원수를 불러오지 못해 30일 상향/하향 애널리스트 행이 비어 있습니다.',
  'tiered.warning.releaseCalendarFailed':
    '{label}의 발표 일정을 불러오지 못해 다음 발표일이 비어 있습니다.',
  'tiered.warning.benchmarkBarsFailed':
    '시장 지수의 가격 이력을 불러오지 못해 이 종목을 시장과 비교할 수 없었습니다.',
  'tiered.warning.benchmarkDateMismatch':
    '시장 지수의 가격 이력은 {index}까지, 이 종목은 {stock}까지 있어 시장 추세와 시장 대비 비교는 둘이 공유하는 마지막 날({through})까지로 계산했습니다.',
  'tiered.warning.newsHeadlinesFailed':
    '기업 뉴스를 가져오지 못해 이 리포트에는 헤드라인이 없습니다. 뉴스 소스 응답: {detail}',
  'tiered.warning.worldNewsBackupFeed':
    'Google News를 가져오지 못해({detail}) 세계 뉴스는 Yahoo Finance 예비 소스에서 가져왔습니다. 예비 소스는 다루는 기사가 적어 이 리포트는 평소보다 빈약할 수 있습니다.',
  'tiered.warning.worldNewsEmptyFeed':
    '세계 뉴스 소스가 오늘 아무 기사도 돌려주지 않아, 이 리포트는 이전 실행에서 가져온 내용만(있다면) 보여줍니다.',
  'tiered.warning.worldNewsFetchFailed': '세계 뉴스를 가져오지 못했습니다. 뉴스 소스 응답: {detail}',
  'tiered.warning.worldNewsUnavailable':
    '세계 뉴스를 사용할 수 없습니다: 가져오기에 실패했고 디스크에 보관된 이전 기사도 없어 이 리포트는 비어 있습니다.',
  'tiered.warning.worldNewsFromPool': '오늘의 소스 대신 이전 실행에서 가져온 기사 {count}건을 보여줍니다.',
  'tiered.warning.worldNewsItemsSkipped':
    '헤드라인, 링크 또는 날짜가 없어 세계 뉴스 {count}건을 건너뛰었습니다.',
  'tiered.warning.worldNewsScreenCap':
    '뉴스가 많은 기간입니다: 기사 {total}건 중 {screened}건을 기간 내 날짜별로 고르게 나눠 선별했습니다.',
  'tiered.warning.sectorBarsFailed':
    '섹터 펀드({ticker})의 가격 이력을 불러오지 못해 섹터 비교 행이 비어 있습니다.',
  'tiered.warning.providerCrashed':
    '{dataReport} 데이터 수집기에서 예기치 않은 오류가 발생해 이번 실행에는 해당 섹션 전체가 빠져 있습니다.',
  'tiered.warning.deepAnalysisCallFailed':
    '심층 분석의 LLM 호출이 실패해 이번 실행에는 전망이 없습니다.',
  'tiered.warning.planReviewCallFailed':
    '계획 검토의 LLM 호출이 실패해 계산된 계획을 그대로 사용합니다.',
  'tiered.warning.planReviewNoReply':
    '계획 검토의 AI 응답을 다시 물어본 뒤에도 읽을 수 없어 계산된 계획을 그대로 사용합니다.',
  'tiered.warning.planReviewSkipped':
    '계획 검토에 필요한 AI 키가 설정되어 있지 않아 계산된 계획을 그대로 사용합니다.',
  'tiered.warning.insufficientHistory':
    '이 종목의 가격 이력이 {bars}일뿐이어서 지표에 필요한 {min}일에 미치지 못해 기술적 분석을 건너뛰었습니다.',
  'tiered.warning.shortDailyHistory':
    '가격 이력이 {bars}일만 확보되어(1년은 약 {year} 거래일) 1년 고가·저가·범위는 완전한 1년이 아닌 확보된 이력만을 반영합니다.',
  'tiered.warning.shortWeeklyHistory':
    '주간 가격 이력이 {bars}주만 확보되어(주간 분석에는 {target}주 필요) 주간 추세를 신뢰할 수 없습니다.',
  'tiered.warning.benchmarkNotConfigured':
    '이 시장에는 시장 지수가 설정되어 있지 않아 종목을 시장과 비교할 수 없었습니다.',
  'tiered.warning.benchmarkShort':
    '시장 지수의 이력이 {bars}일뿐이어서 시장 추세를 판단하거나 수익률을 비교하기에 부족합니다.',
  'tiered.warning.benchmarkShortRegime':
    '시장 지수에 시장 추세 판단에 필요한 200일 이력이 없습니다.',
  'tiered.warning.noImpliedVol':
    '옵션 거래소가 30일 예상 변동폭을 공개하지 않아 내재 변동성 행이 비어 있습니다.',
  'tiered.warning.noOptionsStockPrice':
    '옵션 거래소가 주가를 공개하지 않아 예상 실적 발표일 변동폭을 계산할 수 없었습니다.',
  'tiered.warning.reportDateUnknown':
    '다음 분기 실적 발표일을 알 수 없어 예상 실적 발표일 변동폭을 계산할 수 없었습니다.',
  'tiered.warning.reportDateUnreadable':
    '다음 분기 실적 발표일이 시스템이 읽을 수 없는 형식으로 반환되어 예상 실적 발표일 변동폭을 계산할 수 없었습니다.',
  'tiered.warning.reportTooFarExact':
    '다음 분기 실적 발표까지 {days}일 남아 {max}일을 초과합니다. 그렇게 먼 만기의 옵션 가격은 실적보다 일상적인 변동을 주로 반영하므로 실적 발표일 변동폭을 표시하지 않습니다.',
  'tiered.warning.ratioMissingIngredient':
    '이 비율에는 {field}이(가) 필요하지만 이번 실행에서는 비어 있습니다.',
  'tiered.warningF.daysUntilReport': '다음 분기 실적 발표까지 남은 일수',
  'tiered.warning.noAtmQuotes':
    '실적 발표 후 첫 만기 옵션 계약에 사용할 수 있는 매수/매도 호가가 없어 예상 실적 발표일 변동폭을 계산할 수 없었습니다.',
  'tiered.warning.noPostReportExpiry':
    '불러온 옵션 만기일 중 다음 실적 발표 이후인 것이 없어 예상 실적 발표일 변동폭을 계산할 수 없었습니다.',
  'tiered.warning.noListedOptions':
    '이 종목에는 상장된 옵션이 없어 표시할 옵션 행이 없습니다.',
  'tiered.warning.noShortInterest':
    'Yahoo Finance가 이 종목의 공매도 수치를 공개하지 않아 공매도 행이 비어 있습니다.',
  'tiered.warning.noOwnership':
    'Yahoo Finance가 이 종목의 지분 보유 수치를 공개하지 않아 지분 보유 행이 비어 있습니다.',
  'tiered.warning.noEarningsHistory':
    '이 종목의 과거 분기 실적 기록을 받지 못해 예상치 상회 횟수와 과거 실적 발표일 변동폭 행이 비어 있습니다.',
  'tiered.warning.tooFewReports':
    '불러온 가격 이력 안에 과거 실적 발표가 {count}회뿐이어서 실적 발표일 평균 변동폭을 구하기에 부족합니다.',
  'tiered.warning.fredKeyMissing':
    '경제 데이터 서비스(FRED)의 접근 키가 설정되어 있지 않아 경제 수치를 불러올 수 없었습니다.',
  'tiered.warning.noReleaseDate':
    '{label}의 다음 발표일이 아직 공개되지 않았습니다.',
  'tiered.warning.fomcTableExhausted':
    '내장된 연준 금리 회의 일정표가 마지막 항목을 지나 다음 금리 결정일이 비어 있습니다.',
  'tiered.warning.sectorUnknown':
    '이 회사의 섹터(산업 대분류)를 알 수 없어 섹터 비교 행이 비어 있습니다.',
  'tiered.warning.sectorNoEtf':
    '이 회사의 섹터에 대응하는 섹터 펀드가 아직 설정되어 있지 않아(현재 미국 섹터만 지원) 섹터 비교 행이 비어 있습니다.',
  'tiered.warning.sectorNeedsBenchmark':
    '섹터 비교는 시장 수익률을 기준으로 측정하는데 그 데이터가 없어 섹터 행이 비어 있습니다.',
  'tiered.warning.sectorShort':
    '섹터 펀드({ticker})의 이력이 {bars}일뿐이어서 수익률을 비교하기에 부족해 섹터 행이 비어 있습니다.',
  'tiered.warning.noClosePrice':
    '종가가 없어 매매 계획을 계산할 수 없었습니다.',
  'tiered.warning.noEntryAnchor':
    '진입가의 기준이 되는 가격(50일 이동평균, 200일 이동평균, 가장 가까운 지지선)이 모두 없어 매매 계획을 계산할 수 없었습니다.',
  'tiered.warning.noTechnicalsForLevels':
    '기술적 분석 데이터가 없어 매매 계획을 계산할 수 없었습니다.',
  'tiered.warning.duplicateAdjust':
    'AI가 {level}에 대해 두 번 조정을 제안해 첫 번째만 유지하고 두 번째는 무시했습니다.',
  'tiered.warning.planAdjustDropped':
    'AI가 제안한 {level} 조정의 수치를 리포트에서 뒷받침할 수 없어 해당 조정을 버렸습니다.',
  'tiered.warning.planReplyProblem':
    'AI의 계획 검토 응답에 시스템이 사용할 수 없는 내용이 있어 해당 부분을 무시했습니다.',
  'tiered.warning.planNoConverge':
    'AI가 제안한 모든 조정이 여전히 리스크 검사에 걸려 전부 버리고 계산된 계획을 그대로 사용합니다.',
  'tiered.warning.noGradableFields':
    '작성자가 평가할 리포트 항목이 없어 이번 실행에는 전망이 없습니다.',
  'tiered.warning.noEvidenceToVote':
    '작성자에게 전달된 리포트 데이터가 없어 판단할 내용이 없었습니다. 이 종목을 다시 실행하세요.',
  'tiered.warning.rewardRiskDefaulted':
    '손익비는 1보다 커야 합니다. 입력한 값은 무시하고 기본값을 사용했습니다.',
  'tiered.warning.adjustUnknownLevel':
    'AI가 매매 계획의 가격 수준에 속하지 않는 대상의 조정을 제안해 무시했습니다.',
  'tiered.warning.downtrend':
    '종가가 50일 이동평균 이하입니다. 추세에 역행하는 눌림목 매수는 추가 하락 위험이 큽니다.',
  'tiered.warning.trendCheckSkipped': '50일 이동평균을 사용할 수 없어 추세 검사를 건너뛰었습니다.',
  'tiered.warning.summaryLinksDropped':
    '요약의 일부 인용이 수정 후에도 코드 검증을 통과하지 못했습니다. 해당 수치는 표시되지만 링크는 없습니다.',
  'tiered.warning.optionsOiMissing':
    '데이터 소스에서 옵션 미결제약정이 누락되거나 0으로 반환되어, 풋/콜 미결제약정 비율과 합계는 오해를 부를 수 있는 0 대신 비워 두었습니다.',
  'tiered.warning.optionsVolumeMissing':
    '데이터 소스에서 옵션 거래량이 누락되거나 0으로 반환되어, 풋/콜 거래량 비율은 오해를 부를 수 있는 0 대신 비워 두었습니다.',
  'tiered.warning.insiderRowsMissing':
    'Yahoo가 내부자 거래 행을 하나도 반환하지 않았습니다. 이는 데이터 장애와 구분할 수 없으므로 거래가 없었다고 표시하는 대신 내부자 블록을 비워 두었습니다.',
  // 뉴스 선별 단계(평가/병합/정렬/요약) 저하 — 어느 단계가 실패해도 카드
  // 품질만 낮아질 뿐 뉴스는 절대 버리지 않습니다.
  'tiered.warning.newsJudgeFailed':
    '각 뉴스 기사의 관련성과 중요도를 평가하는 LLM 응답이 누락되거나 읽을 수 없어 모든 기사를 평가 없이 유지했습니다.',
  'tiered.warning.newsJudgeMissing':
    'AI의 뉴스 평가 응답에서 기사 {count}건이 빠져 해당 기사는 평가 없이 유지했습니다.',
  'tiered.warning.newsJudgeUnreadable':
    'AI가 기사 {count}건에 매긴 중요도를 읽을 수 없어 해당 기사는 일단 유지하고 다음 실행에서 다시 평가합니다.',
  'tiered.warning.newsGroupFailed':
    '같은 사건을 다룬 기사를 병합하는 LLM 응답이 누락되거나 읽을 수 없어 병합하지 않았습니다. 같은 사건이 두 번 이상 나타날 수 있습니다.',
  'tiered.warning.newsGroupPartial':
    'AI의 사건 병합 응답에서 기사 {count}건이 빠져 해당 기사는 별도 항목으로 남아 있습니다.',
  'tiered.warning.newsRankFailed':
    '사건을 중요도순으로 정렬하는 LLM 응답이 누락되거나 읽을 수 없어 사건을 중요도 점수순으로 대신 표시합니다.',
  'tiered.warning.newsRankPartial':
    'AI의 정렬 응답에서 사건 {count}건이 빠져 해당 사건은 중요도 점수순으로 맨 뒤에 배치했습니다.',
  'tiered.warning.newsSummaryFailed':
    '한 문장 요약을 작성하는 LLM 응답이 누락되거나 읽을 수 없어 뉴스 피드의 원문 문구를 대신 표시합니다.',
  'tiered.warning.newsSummaryMissing':
    'AI의 요약 응답에서 기사 {count}건이 빠져 해당 항목은 뉴스 피드의 원문 문구를 표시합니다.',
  'tiered.warning.newsTrimmed':
    '뉴스가 많은 시기: 카드에 표시할 수 있는 수보다 많은 사건이 조건을 충족해, 상위 {max}건 아래로 순위가 매겨진 {count}건은 제외했습니다.',
  'tiered.group.trend': '가격 및 추세',
  'tiered.group.momentum': '모멘텀',
  'tiered.group.volatility': '변동성 및 범위',
  'tiered.group.structure': '가격 구조',
  'tiered.group.volume': '거래량',
  'tiered.group.meta': '데이터 및 점수',
  'tiered.group.reportInfo': '리포트 정보',
  'tiered.group.earnings': '실적',
  'tiered.group.other': '기타',
  'tiered.warning.fetchFailed': '뉴스 기사 한 건({domain})을 다운로드하지 못해 사용하지 않았습니다.',
  'tiered.warning.fundamentalsUnavailable':
    '미국 증권거래위원회(SEC) 공식 공시 데이터를 불러오지 못해 일부 펀더멘털 수치가 빠져 있을 수 있습니다.',
  'tiered.warning.valuationUnavailable': 'Yahoo Finance의 밸류에이션 지표를 불러오지 못했습니다.',
  'tiered.warning.macroUnavailable':
    '경제 지표 하나({series})를 FRED 데이터베이스에서 불러오지 못했습니다.',
  'tiered.warning.indicatorNoHistory':
    '가격 이력이 부족해 이 값을 계산할 수 없었습니다.',
  'tiered.warning.macroFieldMissing':
    '데이터 소스가 충분한 데이터를 반환하지 않아 이 값을 계산할 수 없었습니다.',
  'tiered.warning.adjustmentRejected':
    'AI가 {level}을(를) 조정하려 했지만 제안이 규칙에 어긋나 공식으로 계산한 수치를 유지했습니다.',
  'tiered.warning.adjustmentRejectedEarlierKept':
    'AI의 이후 {level} 제안이 규칙에 어긋나 앞서 승인된 값 {value}을(를) 유지했습니다.',
  'tiered.warning.stopFallback':
    '공식으로 계산한 손절가를 사용할 수 없어 변동성(ATR) 기반 손절가를 대신 사용했습니다.',
  'tiered.warning.noAtrStop': '변동성 데이터(ATR)가 없어 손절가를 계산할 수 없었습니다.',
  'tiered.warning.noAtrStopTarget':
    '변동성 데이터(ATR)가 없어 손절가와 목표가 모두 계산할 수 없었습니다.',
  'tiered.warning.noEntryNoStop': '사용할 수 있는 진입가가 없어 손절가를 설정할 수 없었습니다.',
  'tiered.warning.summaryFailed':
    '심층 분석의 서술 요약을 생성하지 못했습니다. 계산된 전망에는 영향이 없습니다.',
  'tiered.warning.badSetting': '포지션 크기 설정 중 하나가 숫자가 아니어서 무시했습니다.',
  'tiered.help.entry':
    '이상적인 매수 가격입니다.\n보통 지지선, 즉 이전에 매수세가 들어왔던 가격 근처입니다.',
  'tiered.help.stopLoss':
    '안전한 출구입니다.\n여기까지 떨어지면 판단이 틀렸다는 뜻이며, 여기서 매도해 손실을 제한합니다.',
  'tiered.help.target': '이익 목표입니다.\n분석이 수익을 확정하기 위해 매도를 권하는 가격입니다.',
  'tiered.empty': '티커를 입력해 티어 분석을 시작하세요.',
  'tiered.history.title': '실행 기록',
  'tiered.status.queued': '대기 중',
  'tiered.status.queuedAt': '대기 중 ({position})',
  'tiered.status.running': '분석 중',
  'tiered.status.succeeded': '성공',
  'tiered.status.failed': '실패',
  'tiered.status.stopped': '중지됨',
  'tiered.help.tier':
    '티어 1(예비 분석): 여섯 개의 데이터 리포트와 전망을 제시하는 LLM 호출 한 번.\n티어 2(심층 분석): 그 단일 호출을 건너뛰고, 두 명의 LLM 작성자가 모든 리포트 항목을 평가해 투표 항목을 만들고 각 투표 항목에 투표합니다. 더 느리지만 더 철저합니다.\n(티어 3은 폐지되었습니다.)',
  'tiered.llmUsage': '이번 실행의 LLM 호출 {calls}회 ({tokens} tokens)',
  'tiered.help.llmUsage':
    '이번 실행이 수행한 LLM 호출 횟수(각각 언어 모델 API에 보낸 요청 한 번)와 총 토큰 수(과금 단위)입니다.\n클릭하면 각 호출의 입력과 출력을 볼 수 있습니다.',
  'tiered.transcript.call': 'LLM 호출 {n}',
  'tiered.transcript.for': '용도',
  'tiered.transcript.llm': 'llm',
  'tiered.transcript.time': '소요 시간',
  'tiered.transcript.tokenCount': '{n} tokens',
  'tiered.transcript.loading': '불러오는 중…',
  'tiered.transcript.error': '대화 기록을 불러올 수 없습니다: {error}',
  'tiered.transcript.empty': '이 실행의 대화 기록은 만료되었습니다(14일 보관).',
  'tiered.transcript.input': '입력',
  'tiered.transcript.output': '출력',
  'tiered.transcript.failed': '호출 실패: {error}',
  'tiered.transcript.noReply': '(응답 없음)',
  'tiered.transcript.callLoading': '불러오는 중…',
  'tiered.transcript.callError': '이 호출을 불러올 수 없습니다: {error}',
  'tiered.kind.formula': '공식',
  'tiered.kind.adjustment': '조정',
  'tiered.kind.whyBlank': '비어 있는 이유',
  'tiered.kind.warnings': '경고',
  'tiered.blankFallback':
    '이번 실행에서 이 항목에는 값이 없습니다. 계산에 필요한 데이터를 사용할 수 없었습니다.',
  'tiered.levelModal.noBase':
    '이번 실행에는 이 가격 수준을 계산하는 데 필요한 데이터가 없어 공식 기준값이 없습니다.',
  'tiered.levelModal.references': '참고 근거',
  'tiered.help.deepAnalysis':
    '두 명의 LLM 작성자가 각자 독립적으로 여섯 개 데이터 리포트(기술적 분석, 펀더멘털, 포지셔닝, 거시경제, 기업 뉴스, 세계 뉴스)의 모든 항목을 강세, 약세, 중립으로 평가합니다. 강세 또는 약세 평가는 1~5점 점수가 붙은 한 문장짜리 투표 항목이 됩니다.\n코드가 인용된 모든 수치를 검증합니다. 수치는 리포트에 표시된 숫자와 정확히 일치하고 문장 안에 나타나야 하며, 실패한 인용은 작성자에게 돌려보내 수정하게 하고(최대 3회), 그래도 고쳐지지 않은 투표 항목은 취소선 처리되어 제외됩니다.\n코드가 두 평가표를 병합하고, 각 투표 항목은 다수결(최대 3표)로 생사가 결정됩니다. 작성자는 유효한 1표로 계산되므로 두 작성자가 같은 방향으로 평가한 항목은 즉시 확정되고, 한 작성자만 올린 투표 항목에는 검증자가 두 번째 표를 던지며, 1 대 1 동점은 결정 투표가 가립니다.\n코드가 살아남은 강세·약세 투표 항목을 점수별로 합산해 전망 점수를 산출합니다. LLM은 숫자에 손대지 않습니다. 마지막 LLM 호출이 투표가 끝난 목록으로 요약을 작성하며, 점수는 요약에 전혀 의존하지 않습니다.',
  'tiered.deepAnalysis.noOutlook':
    '심층 분석에서 전망이 나오지 않았습니다. 종목을 다시 실행하세요(경고 참조).',
  'tiered.tree.bullish': '강세',
  'tiered.tree.bearish': '약세',
  'tiered.tree.valid': '유효',
  'tiered.tree.invalid': '무효',
  'tiered.tree.scores': '점수',
  'tiered.tree.finalScore': '최종 전망 점수',
  'tiered.tree.title': '투표 항목',
  'tiered.tree.loading': '투표 항목을 불러오는 중…',
  'tiered.tree.loadError': '투표 항목을 불러올 수 없습니다: {error}',
  'tiered.tree.howItWorks': '작동 방식',
  'tiered.tree.explain1':
    '두 명의 LLM 작성자가 각자 독립적으로 여섯 개 데이터 리포트(기술적 분석, 펀더멘털, 포지셔닝, 거시경제, 기업 뉴스, 세계 뉴스)의 모든 항목을 강세, 약세, 중립으로 평가합니다. 서로의 결과는 보지 못합니다.',
  'tiered.tree.explain2':
    '강세 또는 약세 평가는 해당 항목의 값을 인용하는 한 문장짜리 투표 항목이 되고, 중립 평가는 아무것도 만들지 않습니다. 투표 항목을 다루는 모든 작성자와 검증자는 1~5점 점수(1 = 매우 사소함, 5 = 매우 중요함)와 이유도 함께 제시합니다.',
  'tiered.tree.explain3':
    '코드가 투표 항목이 인용한 모든 숫자를 리포트와 대조해 검증합니다. 실패한 인용은 작성자에게 돌려보내 수정하게 하고(최대 3회), 그래도 고쳐지지 않은 투표 항목은 취소선 처리되어 어떤 점수에도 계산되지 않습니다.',
  'tiered.tree.explain4':
    '코드가 두 평가표를 병합합니다. 두 작성자가 같은 방향으로 평가한 항목은 작성자가 둘인 하나의 투표 항목이 되며, 이미 2 대 0으로 합의된 상태이므로 검증 표시가 붙지 않습니다.',
  'tiered.tree.explain5':
    '한 작성자만 올린 투표 항목(또는 두 작성자가 반대로 평가한 항목)은 검증자가 검토하며, 항목 뒤의 ✓ 또는 ✗가 그 결과입니다. 표시를 클릭하면 이유를 볼 수 있습니다.',
  'tiered.tree.explain6':
    '그 검증 결과가 무효이면 투표 항목은 1 대 1 동점이 되고, LLM 호출 한 번이 더 결정 투표를 던집니다. 이것이 두 번째 표시입니다. 결정 투표가 없는 동점은 점수에서 제외됩니다.',
  'tiered.tree.explain7':
    '✗가 두 개인 투표 항목은 투표에서 패해 취소선 처리됩니다. 취소선이 없는 항목은 모두 계산되며, 점수는 받은 1~5점 점수 전체의 중앙값입니다. 점수를 클릭하면 이유를 볼 수 있습니다.',
  'tiered.tree.explain8':
    '코드가 최종 전망 점수를 계산합니다: 10 × 강세 투표 항목 점수 합 ÷ 계산된 전체 투표 항목 점수 합. 4 미만 약세, 4~6 중립, 6 초과 강세. LLM은 점수를 쓰지 않습니다.',
  'tiered.tree.explain9':
    '마지막 LLM 호출이 투표가 끝난 목록으로 요약을 작성합니다. 요약의 숫자도 같은 방식으로 인용 검증을 거치며, 요약이 실패해도 계산된 점수는 그대로 유지됩니다.',
  'tiered.tree.codeCheck': '코드 검증 결과',
  'tiered.warning.listerDegradedRole':
    '{role} — 사용할 수 있는 평가표가 돌아오지 않아 이번 실행에서는 다른 작성자의 평가표만 사용했습니다.',
  'tiered.warning.sheetsVoided':
    '두 작성자 모두 사용할 수 있는 평가표를 내지 못해 심층 분석이 무효 처리되었습니다.',
  'tiered.warning.noOutlook':
    '심층 분석에서 전망이 나오지 않았습니다. 종목을 다시 실행하세요.',
  'tiered.warning.preliminaryNoOutlook':
    '예비 분석에서 전망이 나오지 않았습니다. 종목을 다시 실행하세요.',
  'tiered.warning.preliminaryCallFailed':
    '예비 분석의 LLM 호출이 실패해 이번 실행에는 전망이 없습니다.',
  'tiered.warning.preliminaryReplyRejected':
    '예비 분석의 응답을 사용할 수 없어({problem}) 다시 질문했습니다.',
  'tiered.warning.checkDegraded':
    '검증 투표에서 사용할 수 있는 결과가 나오지 않아 투표 항목을 작성자의 표만으로 계산했습니다.',
  'tiered.warning.tiebreakDegraded':
    '결정 투표에서 사용할 수 있는 결과가 나오지 않아 동점인 투표 항목은 미결로 처리하고 점수에서 제외했습니다.',
  'tiered.warning.voteDiscarded':
    '한 표의 인용이 수정 시도 후에도 코드 검증을 통과하지 못해 그 표를 버렸습니다.',
  'tiered.warning.unresolved':
    '한 투표 항목이 결정 투표 없이 1 대 1 동점이 되어 미결로 처리하고 점수에서 제외했습니다.',
  'tiered.warning.allConfirmed':
    '모든 투표 항목을 두 작성자가 독립적으로 올려 검증 투표가 필요하지 않았습니다.',
  'tiered.warning.struckBullet':
    '한 투표 항목의 인용이 3회 수정 시도 후에도 코드 검증을 통과하지 못해 취소선 처리되었고 어떤 점수에도 계산되지 않습니다.',
  'tiered.warning.fixRoundLost': '인용 수정 응답을 읽을 수 없어 그 수정 기회 한 번을 잃었습니다.',
  'tiered.warning.stageRetriedRole':
    '{role} — 첫 응답이 무효였으나 재시도에 성공했습니다.',
  'tiered.warning.stageInvalidRole':
    '{role} — 재시도 후에도 응답이 무효였습니다.',
  'tiered.warning.stageCallFailed':
    '{role} — LLM 호출 자체가 실패해({error}) 심층 분석은 이 단계 없이 진행했습니다.',
  'tiered.role.checkRound': '검증 투표',
  'tiered.role.decidingRound': '결정 투표',
  'tiered.role.reportOutline': '리포트 작성',
  'tiered.role.newsJudge': '뉴스 관련성 판정',
  'tiered.role.newsGrouping': '동일 사건 뉴스 묶기',
  'tiered.role.newsRanking': '뉴스 중요도 정렬',
  'tiered.role.newsSummary': '뉴스 요약 작성',
  'tiered.role.preliminaryAnalysis': '예비 분석',
  'tiered.role.planReview': '계획 검토',
  'tiered.role.citationFix': '{role} (인용 수정)',
  'tiered.warning.stageWrongLanguageRetried':
    '{role} — 첫 응답이 {language}(으)로 작성되지 않아 다시 질문해 바로잡았습니다.',
  'tiered.warning.stageWrongLanguageKept':
    '{role} — {retries}회 다시 질문한 뒤에도 응답이 {language}(으)로 작성되지 않아 원문 그대로 표시합니다.',
  'tiered.languageName.en': '영어',
  'tiered.languageName.zh': '중국어 간체',
  'tiered.warning.emptyLedger': '계산에 남은 투표 항목이 없어 최종 점수는 중립인 5로 기본 설정됩니다.',
  'tiered.warning.thinBase':
    '작성자가 처음 올린 투표 항목 대부분이 살아남지 못해 점수의 근거가 얇습니다.',
  'tiered.help.deepAnalysisScore':
    '심층 분석의 최종 전망 점수로, 10점 만점에 소수점 둘째 자리까지 표시합니다.\n0 = 강한 약세, 5 = 중립, 10 = 강한 강세.\n4 미만 약세, 4~6 중립, 6 초과 강세.\n순수 코드 계산: 10 × 강세 투표 항목 점수 합 ÷ 전체 투표 항목 점수 합이며, 검증을 통과한 투표 항목만 포함합니다. 투표 항목 하단의 점수를 참조하세요.',
  'tiered.help.sizing':
    '고정 산식이며 AI는 관여하지 않습니다.\n모든 숫자는 이 리포트에서 해당 숫자가 나오는 위치로 연결됩니다.\n결과는 정수 주 단위로 내림하며, 한 종목은 자본금의 최대 25%까지만 사용할 수 있습니다.',
  'tiered.form.ticker': '티커',
  'tiered.form.tier': '티어',
  'tiered.form.capital': '자본금',
  'tiered.form.capitalCurrency': '자본금: {currency}',
  'tiered.form.risk': '리스크: %',
  'tiered.form.title': '새 실행',
  'tiered.form.start': '시작',
  'tiered.form.noticeTitle': '알림',
  'tiered.form.needTickerFirst':
    '먼저 티커를 선택하세요. 자본금은 해당 티커가 속한 시장의 통화로 입력합니다.',
  'tiered.form.errorTitle': '오류',
  'tiered.form.missingIntro': '다음 필수 항목이 입력되지 않았습니다:',
  'tiered.form.duplicateRunning':
    '동일한 {ticker} 실행이 이미 진행 중입니다(자본금, 리스크, 손익비, 최대 보유 기간, 티어 모두 동일). 아래 실행 기록에 펼쳐져 있습니다. 완료될 때까지 기다리거나 입력값 중 하나를 바꾸세요.',
  'tiered.form.duplicateQueued':
    '동일한 {ticker} 실행이 이미 대기열에 있습니다(자본금, 리스크, 손익비, 최대 보유 기간, 티어 모두 동일). 아래 실행 기록에 펼쳐져 있으며 자동으로 시작됩니다. 기다리거나 입력값 중 하나를 바꾸세요.',
  'tiered.form.req.ticker': '티커',
  'tiered.form.req.tier': '티어',
  'tiered.form.req.capital': '자본금',
  'tiered.form.req.risk': '리스크',
  'tiered.form.req.reward': '손익비',
  'tiered.form.req.hold': '최대 보유 기간',
  'tiered.form.tierOption1': '1: 예비 분석',
  'tiered.form.tierOption2': '2: 심층 분석',
  'tiered.form.tickerPh': '티커 입력...',
  'tiered.form.tierPh': '티어 입력...',
  'tiered.form.capitalPh': '자본금 입력...',
  'tiered.form.riskPh': '리스크 입력...',
  'tiered.form.reward': '손익비: x',
  'tiered.form.rewardPh': '손익비 입력...',
  'tiered.form.lowRewardWarn':
    '손익비가 1.5 미만이면 거래가 리스크를 간신히 감당하는 수준입니다. 일반적인 최소 기준은 1.5×입니다. 이번 실행은 그래도 입력한 {value}× 목표를 사용합니다.',
  'tiered.help.reward':
    '계획에 요구하는 손익비(잠재 이익이 감수하는 리스크의 몇 배여야 하는지)입니다. 필수이며 기본값은 2입니다.\n목표가 = 진입가 + 손익비 × 리스크. 위쪽 저항선이 목표가를 요구한 배율 아래로 제한하면 계획에 경고가 붙습니다(하한선인 1.5 미만이면 계획을 아예 제시하지 않습니다).',
  'tiered.form.hold': '최대 보유 기간: 주',
  'tiered.form.holdPh': '최대 보유 기간 입력...',
  'tiered.help.hold':
    '이 거래를 보유할 최장 기간입니다. 필수이며 기본값은 2주입니다.\n같은 숫자가 AI(이 기간에 어떤 근거가 중요한지 판단), 리포트, 그리고 사후 검증의 평가 기간에 그대로 쓰여 AI와 사용자와 검증이 하나의 시간 범위를 공유합니다.',
  'tiered.form.marketOpenTitle': '시장 개장 중',
  'tiered.form.marketOpenTrading':
    '{market} 시장이 지금 거래 중입니다. 이 앱은 완료된 거래일만 분석하므로 오늘은 아직 분석할 데이터가 없습니다.',
  'tiered.form.marketOpenHours':
    '오늘 거래 시간: {open}–{close}(시장 현지 시간), 사용자 시간대로는 {openLocal}–{closeLocal}입니다.',
  'tiered.form.marketOpenMixedData':
    '“그래도 실행”은 직전 완료된 거래일을 분석합니다. 기술적 분석 리포트는 그날 종가까지의 데이터만 사용하지만 뉴스 등 다른 소스는 실시간일 수 있어, 리포트 안에 서로 다른 두 시점의 데이터가 섞일 수 있습니다.',
  'tiered.form.marketOpenBestWindow':
    '또한 장 마감 후에도 데이터 소스가 실시간 데이터보다 최대 30분 늦을 수 있고 실행 자체에도 시간이 걸리므로, 앱을 사용하기 가장 좋은 때는 장 마감 30분 후부터 다음 개장 30분 전까지입니다.',
  'tiered.form.runAnyway': '그래도 실행',
  'tiered.pill.ticker': '티커: {value}',
  'tiered.pill.tier': '티어: {value}',
  'tiered.pill.capital': '자본금: {value} {currency}',
  'tiered.pill.risk': '리스크: {value}%',
  'tiered.pill.reward': '손익비: {value}×',
  'tiered.pill.hold': '최대 보유 기간: {value}주',
  'tiered.pill.capitalMin': '자본금 하한: {value}',
  'tiered.pill.capitalMax': '자본금 상한: {value}',
  'tiered.pill.riskPctMin': '리스크 하한: {value}%',
  'tiered.pill.riskPctMax': '리스크 상한: {value}%',
  'tiered.pill.dateMin': '시작일: {value}',
  'tiered.pill.dateMax': '종료일: {value}',
  'tiered.pill.rewardRatioMin': '손익비 하한: {value}×',
  'tiered.pill.rewardRatioMax': '손익비 상한: {value}×',
  'tiered.filter.tickerPh': '티커 입력...',
  'tiered.filter.capital': '자본금',
  'tiered.filter.risk': '리스크: %',
  'tiered.filter.date': '날짜: yyyy/mm/dd',
  'tiered.filter.tier': '티어',
  'tiered.filter.tierPh': '티어 입력...',
  'tiered.filter.holdPh': '최대 보유 기간 입력...',
  'tiered.filter.reward': '손익비: ×',
  'tiered.filter.min': '하한',
  'tiered.filter.max': '상한',
  'tiered.history.shares': '{value}주',
  'tiered.history.tier': '티어 {value}',
  'tiered.history.hold': '{value}주간',
  // 실행 목록의 열 이름 헤더 행.
  'tiered.history.h.ticker': '티커',
  'tiered.history.h.capital': '자본금',
  'tiered.history.h.risk': '리스크',
  'tiered.history.h.reward': '손익비',
  'tiered.history.h.hold': '최대 보유 기간',
  'tiered.history.h.tier': '티어',
  'tiered.history.h.status': '상태',
  'tiered.history.h.outlook': '전망',
  'tiered.history.h.date': '날짜',
  'tiered.history.first': '첫 페이지',
  'tiered.history.prev': '이전 페이지',
  'tiered.history.next': '다음 페이지',
  'tiered.history.last': '마지막 페이지',
  'tiered.history.none': '필터에 맞는 실행이 없습니다',
  'tiered.history.loading': '리포트 불러오는 중…',
  'tiered.history.delete': '이 실행 삭제',
  'tiered.history.cancel': '이 실행 취소',
  'tiered.history.deleteAsk': '이 실행과 LLM 대화 기록을 삭제할까요? 되돌릴 수 없습니다.',
  'tiered.history.cancelAsk': '이 실행을 대기열에서 뺄까요? 시작되지 않습니다.',
  'tiered.history.confirmDelete': '삭제',
  'tiered.history.confirmCancel': '실행 취소',
  'tiered.history.keep': '유지',
  'tiered.history.deleting': '삭제 중…',
  'tiered.history.deleteInProgress': '이 실행은 진행 중이어서 삭제할 수 없습니다. 먼저 중지한 뒤 삭제하세요.',
  'tiered.history.deleteError': '삭제할 수 없습니다: {error}',
  'tiered.history.stop': '이 실행 중지',
  'tiered.history.stopAsk': '이 실행을 중지할까요? 완료된 부분은 보고서에 남고 나머지는 분석하지 않습니다. 진행 중인 모델 호출은 끝까지 완료되어 집계됩니다.',
  'tiered.history.confirmStop': '실행 중지',
  'tiered.history.stopping': '중지 중…',
  'tiered.history.stopNotRunning': '이 실행은 더 이상 진행 중이 아닙니다.',
  'tiered.history.stopError': '중지할 수 없습니다: {error}',
  'tiered.dataReports.title': '데이터 리포트',
  'tiered.eventsNone': '최근 {count}일 내 없음',
  'tiered.eventsNoneGeneric': '없음',
  'tiered.eventsWindow': '최근 {count}일',
  'tiered.deepAnalysis.title': '심층 분석',
  'tiered.rewardBelowGoal':
    '이 계획의 손익비는 {ratio}로, 목표인 {goal}×에 미치지 못합니다. 위쪽 저항선이 목표가를 제한합니다.',
  'tiered.roundLevelTitle': '라운드 넘버',
  'tiered.roundLevelBody':
    '{value}은(는) 현재가 아래에서 가장 가까운 라운드 넘버 가격입니다. 어떤 데이터 행에서 온 것이 아니라 코드가 즉석에서 계산합니다. 주문이 라운드 넘버에 몰리는 경향이 있어 약한 지지선을 이룹니다.',
  'tiered.f.capital': '자본금',
  'tiered.f.risk': '거래당 리스크',
  'tiered.f.entry': '진입가',
  'tiered.f.stop': '손절가',
  'tiered.sources': '출처',
  'tiered.levels.computed': '계산값',
  'tiered.levels.adjusted': '조정값',
  'tiered.levels.keep': '유지',
  'tiered.levels.shares': '수량',
  'tiered.levels.warnings': '경고',
  'tiered.warn.none': '없음',
  'tiered.warn.downtrend':
    '종가({close})가 60일 이동평균({sma60}) 이하입니다. 종목이 중기 하락 추세에 있어 여기서 진입하면 추세에 역행하는 매수가 되고 추가 하락 위험이 커집니다.',
  'tiered.warn.downtrend_50':
    '종가({close})가 50일 이동평균({sma50}) 이하입니다. 종목이 중기 하락 추세에 있어 여기서 진입하면 추세에 역행하는 매수가 되고 추가 하락 위험이 커집니다.',
  'tiered.warn.earnings_soon':
    '다음 실적 발표가 {days}일 뒤({date})로 일반적인 스윙 보유 기간 안에 있습니다. 기술적 분석은 실적 발표를 버티지 못합니다. 발표 한 번으로 가격이 어떤 손절가든 갭으로 뛰어넘을 수 있습니다. 발표 전에 청산하거나 갭을 감안해 수량을 줄이세요.',
  'tiered.warn.macro_event_soon':
    '{event}이(가) {days}일 뒤({date})로 일반적인 스윙 보유 기간 안에 있습니다. 이는 시장 전체의 갭 리스크로, 숫자 하나가 모든 종목을 한꺼번에 움직일 수 있습니다. 그 시기에는 수량을 줄이거나 갭을 감안해 손절가를 정하세요.',
  'tiered.warnEvent.rate_decision': '다음 공식 금리 결정',
  'tiered.warnEvent.inflation_data': '다음 물가 지표 발표',
  'tiered.warnEvent.employment_data': '다음 고용 지표 발표',
  'tiered.warn.gap_atr':
    '밤사이 뉴스로 시가가 손절가({stop})보다 1 ATR({atr}) 아래로 갭 하락하면 {atrOpen}에 시작합니다. 손절 주문은 그 가격에 체결되어 {atrLoss}의 손실이 나며, 계획한 {planned}보다 {atrExtra} 더 큽니다.',
  'tiered.warn.gap_worst':
    '지난 1년 최악의 하루({worstDayPct}%)가 반복되면 시가는 손절가({stop})를 지나 {worstOpen}에 형성됩니다. 그 가격에 매도하면 {worstLoss}의 손실이 나며, 계획한 {planned}보다 {worstExtra} 더 큽니다.',
  // 경고 팝업의 계산값 이름 (공식 설명 줄의 변수명으로도 사용).
  'tiered.warnF.gapOpen': '갭 시가',
  'tiered.warnF.gapLoss': '갭 손실',
  'tiered.warnF.plannedLoss': '계획 손실',
  'tiered.warnF.worstOpen': '최악의 날 시가',
  'tiered.warnF.worstLoss': '최악의 날 손실',
  'tiered.warnF.ratio': '손익비',
  'tiered.f.shares': '수량',
  'tiered.f.target': '목표가',
  // 각 리스크 문장이 시작하는 고정 키워드 (검사 id에서 코드가 고름, AI가 쓰지 않음).
  'tiered.warnKey.downtrend': '하락 추세',
  'tiered.warnKey.earnings_soon': '실적 발표 임박',
  'tiered.warnKey.macro_event_soon': '거시경제 이벤트 임박',
  'tiered.warnKey.gap_atr': '밤사이 갭 리스크',
  'tiered.warnKey.gap_worst': '최악의 날 갭 리스크',
  'tiered.warnKey.reward_below_goal': '낮은 손익비',
  'tiered.checkKey.downtrend': '하락 추세',
  'tiered.checkKey.liquidity': '유동성',
  'tiered.checkKey.volatility': '변동성',
  'tiered.checkKey.stop_vs_support': '지지선',
  'tiered.reviewFail.title': '계획이 계산값을 유지하는 이유',
  'tiered.reviewFail.intro':
    'AI가 이 계획을 조정하려 했지만 매번 리스크 검사에 걸려 모든 조정을 버리고 공식으로 계산한 계획을 그대로 사용합니다.',
  'tiered.reviewFail.round': '{round}회차 조정 후에도 걸림: {checks}',
  'tiered.help.capital':
    '거래에 쓰는 자금으로, 티커가 속한 시장의 통화로 입력합니다.\n수량 계산의 출발점입니다.\n다음 실행을 위해 기억됩니다.',
  'tiered.help.riskPct':
    '한 거래에서 감수할 수 있는 최대 손실로, 자본금 대비 백분율입니다.\n1~2%가 일반적입니다.',

  // ---- 전망 개편 (outlook redesign) ----
  'tiered.preliminaryAnalysis.title': '예비 분석',
  'tiered.outlook': '전망',
  'tiered.action': '조치',
  'tiered.actionRatio': '현재 손익비는 {ratio}입니다',
  'tiered.outlook.bullish': '강세',
  'tiered.outlook.neutral': '중립',
  'tiered.outlook.bearish': '약세',
  'tiered.outlook.no_outlook': '전망 없음',
  'tiered.action.buy_now': '지금 매수',
  'tiered.action.buy_later': '나중에 매수',
  'tiered.action.no_trade': '거래 안 함',
  'tiered.action.unknown': '다시 실행 — 이번 실행에서 사용할 수 있는 전망이 나오지 않았습니다',
  'tiered.help.outlook':
    '전망은 보유 여부와 관계없이 종목 자체에 대한 판단(강세 / 중립 / 약세)입니다.\n조치는 코드가 전망에서 도출합니다: 강세 → 지금 매수(매매 계획의 손익비가 목표를 충족) 또는 나중에 매수(목표에 미달), 중립 또는 약세 → 거래 안 함.',
  'tiered.help.action':
    '고정된 코드 규칙이 전망에서 도출한 개인 조치 안내입니다.\n강세는 둘로 나뉩니다. 매매 계획의 실제 손익비가 설정한 목표에 도달하면 “지금 매수”, 미달하면(예: 위쪽 저항선이 목표가를 제한) “나중에 매수”(더 좋은 가격을 기다렸다가 진입).',
  'tiered.staleWarning':
    '이 리포트는 이전 거래일의 것입니다. 최신 계획을 보려면 다시 실행하세요.',
  'tiered.tradePlan.title': '매매 계획',
  'tiered.help.plan':
    '고정 공식이 가격 데이터로 계산한 계획 가격 수준입니다(LLM 미사용).\n표시 내용은 조치에 따라 달라집니다: 지금 매수 또는 나중에 매수 → 전체 가격표, 거래 안 함 → 가격 없음.',
  'tiered.filter.status': '상태',
  'tiered.filter.statusPh': '상태 입력...',
  'tiered.pill.status': '상태: {value}',
  'tiered.filter.outlook': '전망',
  'tiered.filter.outlookPh': '전망 입력...',
  'tiered.pill.outlook': '전망: {value}',

  'tiered.tree.bullishScoreSum': '강세 점수 합',
  'tiered.tree.totalScoreSum': '전체 점수 합',

  // ---- 티어 2 상세 (v11: 1~5점 점수 + 점수 이유) ----
  'tiered.tree.lister': '작성자 {n}',
  'tiered.tree.checker': '검증자 {n}',
  'tiered.tree.validityLine': '결과: {value}',
  'tiered.tree.reasonPrefix': '이유:',
  'tiered.tree.scoreLine': '점수: {value}',
  'tiered.tree.scoresList': '점수: {value}',
  'tiered.tree.medianTitle': '점수',
  'tiered.tree.medianLine': '중앙값: {value}',

  // 채팅 페이지 (2026-09-21): 봇이 앱 자체의 API를 통해 읽고 동작합니다.
  'chat.sidebar.title': '기록',
  'chat.new': '새 대화',
  'chat.facts.inputs': '대화 턴',
  'chat.facts.tokens': '사용한 tokens',
  'chat.facts.start': '시작일',
  'chat.facts.end': '종료일',
  'chat.sidebar.delete': '이 대화 삭제',
  'chat.sidebar.deleteAsk': '이 대화를 삭제할까요? 되돌릴 수 없습니다.',
  'chat.sidebar.confirmDelete': '삭제',
  'chat.sidebar.keep': '유지',
  'chat.empty.hint':
    '이 ReAct 에이전트는 주 LLM으로 구동됩니다. 이 앱 전반을 이해하고 있으며 사용자가 쓸 수 있는 모든 API에 접근할 수 있습니다. 단, 소스 코드에는 접근할 수 없습니다.',
  'chat.composer.placeholder': 'Enter = 전송, Shift+Enter = 줄바꿈',
  'chat.composer.send': '전송',
  'chat.composer.stop': '중지',
  'chat.composer.stopping': '현재 단계가 끝나면 중지합니다…',
  'chat.stopped.during': '{n}단계에서 답변을 중지했습니다. {n}단계는 완료되었습니다.',
  'chat.stopped.nextTool': '{n}단계에서는 도구 {tool}을(를) 호출할 예정이었습니다.',
  'chat.stopped.nextLlm': '{n}단계에서는 LLM이 다음에 무엇을 할지 결정하도록 할 예정이었습니다.',
  'chat.stopped.last': '그것이 마지막 단계였습니다.',
  'chat.error.stop': '중지할 수 없습니다: {error}',
  'chat.composer.waitConfirm': '먼저 위의 질문에 답해 주세요.',
  'chat.composer.waitTurn': '답변을 기다리는 중입니다. 입력은 가능하며 /help는 바로 답합니다.',
  'chat.step.tool': '{n}단계: LLM이 도구 호출을 결정',
  'chat.step.say': '{n}단계: LLM이 답변을 결정',
  'chat.step.failed': '{n}단계: LLM 호출 실패',
  'chat.step.toolCall': '{n}단계: 도구 호출',
  'chat.tool.name': '이름',
  'chat.tool.decision': '결정',
  'chat.tool.approve': '승인',
  'chat.tool.decline': '거부',
  'chat.tool.status': '상태',
  'chat.tool.status.waiting': '대기 중',
  'chat.tool.status.processing': '처리 중',
  'chat.tool.status.succeeded': '성공',
  'chat.tool.status.failed': '실패',
  'chat.tool.approved': '승인됨',
  'chat.tool.declined': '거부됨',
  'chat.tool.truncated': '모델은 잘라낸 사본을 보았습니다.',
  'chat.tool.input': '입력',
  'chat.tool.output': '출력',
  'chat.usage': '이 단계에서 {tokens} tokens 사용',
  'chat.step.noUsage': '이 단계는 tokens를 보고하지 않았습니다',
  'chat.transcript.missing': '이 답변의 대화 기록은 보관되지 않았습니다(2026-09-23 이전 답변에는 기록이 없습니다).',
  'chat.help.usage':
    '이 LLM 호출이 사용한 tokens(과금 단위)입니다. 호출마다 기본 지시문, 도구 목록, 전체 대화를 다시 보내므로 "hi" 한 마디에도 수천 개가 듭니다.\n클릭하면 정확한 프롬프트와 응답을 볼 수 있습니다.',
  'chat.notice.toolCallLimit': '봇이 한 턴의 도구 호출 한도에 도달해 멈췄습니다.',
  'chat.notice.wrongLanguage': '이 답변은 선택한 언어가 아닙니다.',
  'chat.error.busy': '봇이 아직 이전 메시지를 처리하고 있습니다.',
  'chat.error.notConfigured': '모델이 설정되어 있지 않습니다. 먼저 .env에 MAIN_LLM과 LLM_API_KEY를 설정하세요.',
  'chat.error.send': '전송할 수 없습니다: {error}',

  // 슬래시 명령(2026-10-13): 입력창에서 "/"로 시작하는 줄은 봇에게 보내는 메시지가 아니라 명령입니다.
  'chat.command.menu': '명령',
  'chat.command.unknown': '알 수 없는 명령 {command}입니다. /help를 입력하면 명령 목록을 볼 수 있습니다.',
  'chat.command.help.title': '명령',
  'chat.command.help.help': '명령 목록을 보여줍니다.',
  'chat.command.help.context': '이 대화가 LLM 컨텍스트를 얼마나 차지하는지 보여줍니다.',
  'chat.command.help.compact': '지금까지의 대화를 요약해 컨텍스트 공간을 비웁니다.',
  'chat.command.help.btw': 'LLM에게 번외 질문을 합니다. 이후 대화에서는 기억하지 않습니다.',
  'chat.command.btw.argument': '질문',
  'chat.command.needsArgument': '/{command} 뒤에 {hint}을(를) 입력해 주세요.',
  'chat.step.sideQuestion': '{n}단계: LLM이 번외 질문에 답했습니다',
  'chat.sideQuestion.note': '번외 질문입니다. 이후 대화에서 LLM은 이 질문과 답변을 보지 않습니다.',
  'chat.context.title': 'LLM 컨텍스트 창 사용량',
  'chat.context.llm': 'LLM',
  'chat.context.noLlm': '설정된 모델 없음',
  'chat.context.window': '컨텍스트 창',
  'chat.context.windowValue': '{max} = {window}(최대) - {reserved}(LLM 답변용 예약)',
  'chat.command.waitTurn': '답변이 돌아온 뒤에 /{command}를 사용해 주세요.',
  'chat.context.usage': '사용량',
  'chat.context.usageValue': '{used}({percent}%) = {system}(지시문) + {tools}(도구) + {conversation}(대화)',
  'chat.step.summary': '{n}단계: LLM이 대화를 요약함',
  'chat.step.summaryFailed': '{n}단계: 요약 실패',
  'chat.summary.failed': '요약에 실패해 LLM은 여전히 모든 메시지를 봅니다. 다음 메시지에서 다시 시도하며, /compact를 입력해도 됩니다.',
  'chat.error.nothingToCompact': '아직 요약할 내용이 없습니다. 먼저 메시지를 보내 주세요.',

};
