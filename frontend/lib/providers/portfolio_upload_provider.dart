import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/portfolio_data.dart';

/// 사용자가 업로드한 포트폴리오 데이터를 보관하는 Notifier
/// null = 업로드 없음 → 서버 portfolio.json 사용
class PortfolioUploadNotifier extends Notifier<PortfolioData?> {
  @override
  PortfolioData? build() => null;

  void setPortfolio(PortfolioData data) => state = data;
  void clearPortfolio() => state = null;
}

final portfolioUploadProvider =
    NotifierProvider<PortfolioUploadNotifier, PortfolioData?>(
  PortfolioUploadNotifier.new,
);
