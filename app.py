import streamlit as st
import yaml
import json
from datetime import datetime
from typing import List, Dict, Any, Optional, TypedDict
import mlflow.deployments
import os
from databricks import sql
import uuid
import pandas as pd


# 設定ファイルの読み込み
def load_config():
    """YAMLファイルから設定を読み込む"""
    try:
        with open('config.yaml', 'r', encoding='utf-8') as file:
            config = yaml.safe_load(file)
        return config
    except Exception as e:
        st.error(f"設定ファイルの読み込みエラー: {e}")
        # デフォルト値を返す（実際はもっと簡略化されたバージョン）
        return {
            "PERSONA_OPTIONS": ["データエンジニア", "データサイエンティスト"],
            "INTEREST_OPTIONS": ["データガバナンス", "生成AI"],
            "NEXT_ACTION_OPTIONS": ["詳細製品説明", "製品デモ"],
            "CLOUD_OPTIONS": ["AWS", "Azure", "GCP", "オンプレミス"],
            "DATA_STACK": {"データエンジニアリング": ["ジョブ管理", "データ取り込み"]},
            "PERSONA_STACK_MAPPING": {"データエンジニア": ["ジョブ管理"]},
            "COMMON_ISSUES": {"ジョブ管理": ["スケジューリングが複雑"]},
            "PRODUCTS_BY_CLOUD": {"AWS": {"ジョブ管理": ["AWS Step Functions"]}},
            "DATABRICKS_CONTRIBUTIONS": {},
            "DEEPDIVE_QUESTIONS": {},
            "ISSUE_SPECIFIC_QUESTIONS": {},
            "ISSUE_SPECIFIC_CONTRIBUTIONS": {}
        }

# 設定の読み込み
CONFIG = load_config()

# Constants from config
PERSONA_OPTIONS = CONFIG["PERSONA_OPTIONS"]
INTEREST_OPTIONS = CONFIG["INTEREST_OPTIONS"]
NEXT_ACTION_OPTIONS = CONFIG["NEXT_ACTION_OPTIONS"]
CLOUD_OPTIONS = CONFIG["CLOUD_OPTIONS"]
DATA_STACK = CONFIG["DATA_STACK"]
PERSONA_STACK_MAPPING = CONFIG["PERSONA_STACK_MAPPING"]
COMMON_ISSUES = CONFIG["COMMON_ISSUES"]
PRODUCTS_BY_CLOUD = CONFIG["PRODUCTS_BY_CLOUD"]
DATABRICKS_CONTRIBUTIONS = CONFIG["DATABRICKS_CONTRIBUTIONS"]
DEEPDIVE_QUESTIONS = CONFIG["DEEPDIVE_QUESTIONS"]
ISSUE_SPECIFIC_QUESTIONS = CONFIG["ISSUE_SPECIFIC_QUESTIONS"]
ISSUE_SPECIFIC_CONTRIBUTIONS = CONFIG["ISSUE_SPECIFIC_CONTRIBUTIONS"]

# Set page configuration
st.set_page_config(
    page_title="DiscoveryDojo",
    page_icon="🔄",
    layout="wide"
)

# CSSファイルを読み込む
def load_css():
    try:
        with open('styles.css', 'r', encoding='utf-8') as f:
            css = f.read()
        st.markdown(f'<style>{css}</style>', unsafe_allow_html=True)
    except Exception as e:
        st.warning(f"スタイルシートの読み込みエラー: {e}")
        # 基本的なスタイルをインラインで適用
        st.markdown("""
        <style>
        .stButton>button {
            width: 100%;
            min-width: 100px;
        }
        h1, h2, h3 {
            color: #ff3621;
        }
        </style>
        """, unsafe_allow_html=True)

# CSSを読み込む
load_css()

# Simple State Manager class
class StateManager:
    def __init__(self):
        self.state = None
        self.initialize()
        
    def initialize(self):
        """Initialize a new state"""
        # Create default state
        self.state = {
            "customer_info": {},
            "platform_data": {
                "AWS": [],
                "Azure": [],
                "GCP": [],
                "オンプレミス": []
            },
            "project_data": {},
            "next_actions": [],
            "current_step": "customer_info",
            "current_cloud": "AWS"
        }
        return self.state["current_step"]
    
    def update_customer_info(self, customer_info):
        """Update customer basic information"""
        if not isinstance(customer_info, dict):
            print("Error: customer_info is not a dictionary")
            return self.state["current_step"]
            
        self.state["customer_info"] = customer_info.copy()
        self.state["current_step"] = "platform_discovery"
        
        return self.state["current_step"]
    
    def update_platform_data(self, platform_data, cloud):
        """Update platform data for a specific cloud"""
        if not isinstance(platform_data, list):
            print("Error: platform_data is not a list")
            return self.state["current_step"]
            
        self.state["platform_data"][cloud] = platform_data.copy()
        self.state["current_cloud"] = cloud
        self.state["current_step"] = "platform_discovery"
            
        return self.state["current_step"]
    
    def move_to_project_data(self):
        """Move to project data step"""
        self.state["current_step"] = "project_data"
        return self.state["current_step"]
    
    def update_project_data(self, project_data):
        """Update project data information"""
        self.state["project_data"] = project_data
        self.state["current_step"] = "next_actions"
        return self.state["current_step"]
    
    def update_next_actions(self, next_actions):
        """Update next actions"""
        self.state["next_actions"] = next_actions
        self.state["current_step"] = "summary"
        return self.state["current_step"]
    
    # StateManager クラスに以下のメソッドを追加
    def get_state(self):
        """Get the current state"""
        return self.state

    def set_state(self, new_state):
        """Set entire state from external source"""
        if not isinstance(new_state, dict):
            print("Error: new_state is not a dictionary")
            return self.state["current_step"]
            
        self.state = new_state.copy()
        return self.state["current_step"]

    def get_id(self):
        """Get current state ID"""
        return self.state.get("id", None)

    def set_id(self, state_id):
        """Set state ID"""
        self.state["id"] = state_id
        return state_id

# DeltaTableManager クラスを追加
class DeltaTableManager:
    def __init__(self, config):
        """Initialize the DeltaTableManager"""
        self.config = config
        self.catalog = os.environ.get("CATALOG_NAME", config["DELTA_TABLE"]["DEFAULT_CATALOG"])
        self.schema = os.environ.get("SCHEMA_NAME", config["DELTA_TABLE"]["DEFAULT_SCHEMA"])
        self.table_name = config["DELTA_TABLE"]["TABLE_NAME"]
        self.full_table_name = f"{self.catalog}.{self.schema}.{self.table_name}"
        self._init_connection()
        self._ensure_table_exists()
        
    def _init_connection(self):
        """Initialize connection to Databricks SQL"""
        try:
            # 環境変数から接続情報を取得
            server_hostname = os.environ.get("DATABRICKS_SERVER_HOSTNAME")
            http_path = os.environ.get("DATABRICKS_HTTP_PATH")
            access_token = os.environ.get("DATABRICKS_TOKEN")
            
            if not server_hostname or not http_path:
                st.warning("Databricks接続情報が設定されていません。履歴機能は無効です。")
                self.connection = None
                return
                
            self.connection = sql.connect(
                server_hostname=server_hostname,
                http_path=http_path,
                access_token=access_token
            )
        except Exception as e:
            st.error(f"Delta Tableへの接続エラー: {e}")
            self.connection = None
    
    def _ensure_table_exists(self):
        """Ensure that the history table exists"""
        if not self.connection:
            return
            
        try:
            with self.connection.cursor() as cursor:
                # Check if table exists
                cursor.execute(f"""
                    CREATE TABLE IF NOT EXISTS {self.full_table_name} (
                        id STRING,
                        company STRING, 
                        record_date TIMESTAMP,
                        recorder STRING,
                        state_json STRING
                    )
                    USING DELTA
                """)
        except Exception as e:
            st.error(f"Delta Table作成エラー: {e}")
    
    def save_state(self, state):
        """Save state to Delta table"""
        if not self.connection:
            return None
            
        try:
            # Generate new ID if not exists
            if "id" not in state or not state["id"]:
                state["id"] = str(uuid.uuid4())
            
            # Extract basic info
            state_id = state["id"]
            company = state.get("customer_info", {}).get("company", "不明")
            recorder = state.get("customer_info", {}).get("writer", "不明")
            record_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Convert state to JSON
            state_json = json.dumps(state, ensure_ascii=False)
            
            with self.connection.cursor() as cursor:
                # Check if record exists
                cursor.execute(f"""
                    SELECT COUNT(*) FROM {self.full_table_name}
                    WHERE id = '{state_id}'
                """)
                count = cursor.fetchone()[0]
                
                if count > 0:
                    # Update existing record
                    cursor.execute(f"""
                        UPDATE {self.full_table_name}
                        SET company = '{company}',
                            record_date = '{record_date}',
                            recorder = '{recorder}',
                            state_json = '{state_json}'
                        WHERE id = '{state_id}'
                    """)
                else:
                    # Insert new record
                    cursor.execute(f"""
                        INSERT INTO {self.full_table_name}
                        VALUES ('{state_id}', '{company}', '{record_date}', '{recorder}', '{state_json}')
                    """)
                    
            return state_id
        except Exception as e:
            st.error(f"状態の保存エラー: {e}")
            return None
    
    def get_history_list(self):
        """Get list of all history records"""
        if not self.connection:
            return []
            
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(f"""
                    SELECT id, company, record_date, recorder
                    FROM {self.full_table_name}
                    ORDER BY record_date DESC
                """)
                
                # Convert to list of dicts
                columns = [col[0] for col in cursor.description]
                history = [dict(zip(columns, row)) for row in cursor.fetchall()]
                
                return history
        except Exception as e:
            st.error(f"履歴の取得エラー: {e}")
            return []
    
    def get_state_by_id(self, state_id):
        """Get state by ID"""
        if not self.connection:
            return None
            
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(f"""
                    SELECT state_json
                    FROM {self.full_table_name}
                    WHERE id = '{state_id}'
                """)
                
                result = cursor.fetchone()
                if result:
                    return json.loads(result[0])
                return None
        except Exception as e:
            st.error(f"状態の取得エラー: {e}")
            return None
    
    def delete_history(self, state_id):
        """Delete history record by ID"""
        if not self.connection:
            return False
            
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(f"""
                    DELETE FROM {self.full_table_name}
                    WHERE id = '{state_id}'
                """)
            return True
        except Exception as e:
            st.error(f"履歴の削除エラー: {e}")
            return False

# AI Model Service
class AIModelService:
    def __init__(self):
        # Initialize the Databricks model deployment
        # In a real application, we would connect to the actual model
        # For this example, we'll use a mock implementation
        pass
    
    def generate_deep_dive_question(self, stack_component, issues):
        """Generate deep dive question based on stack component and issues"""
        # 基本的な質問を取得
        base_question = DEEPDIVE_QUESTIONS.get(
            stack_component, 
            "この技術スタックについて、現在どのような具体的な課題に直面していますか？"
        )
        
        # 課題固有の質問を追加
        issue_specific_questions = ""
        if issues:
            for issue in issues:
                if issue in ISSUE_SPECIFIC_QUESTIONS:
                    issue_specific_questions += ISSUE_SPECIFIC_QUESTIONS[issue] + " "
        
        if issue_specific_questions:
            return base_question + " " + issue_specific_questions
        return base_question
    
    def generate_summary(self, state: Dict[str, Any]) -> str:
        """Generate a summary of all collected information"""
        # In a real application, this would call a deployed LLM
        # For this example, we'll create a formatted text summary
        
        customer_info = state.get("customer_info", {})
        platform_data = state.get("platform_data", {})
        project_data = state.get("project_data", {})
        next_actions = state.get("next_actions", [])
        
        summary = f"""
## DiscoveryDojo調査サマリー

### 記入者情報
- 面談日: {customer_info.get('meeting_date', '不明')}
- 記入者: {customer_info.get('writer', '不明')}

### 顧客情報
- 社名: {customer_info.get('company', '不明')}
- 部署: {customer_info.get('department', '不明')}
- 担当者: {customer_info.get('person', '不明')}
- ペルソナ: {customer_info.get('persona', '不明')}
- 関心領域: {customer_info.get('interest', '不明')}

### 現在の技術スタック状況
"""
        
        # Collect all components across all clouds for better organization in summary
        all_components = set()
        for cloud, stacks in platform_data.items():
            for stack in stacks:
                if isinstance(stack, dict) and "component" in stack:
                    all_components.add(stack.get("component", ""))
        
        # Track which components have been included in the summary
        included_components = set()
                
        # Group the summary by cloud
        for cloud, stacks in platform_data.items():
            if stacks:
                summary += f"\n#### {cloud}\n"
                for stack in stacks:
                    if not isinstance(stack, dict):
                        continue
                        
                    component = stack.get("component", "")
                    if not component:
                        continue
                        
                    product = stack.get("product", "")
                    cost = stack.get("cost", "不明")
                    issues = stack.get("issues", [])
                    details = stack.get("details", "")
                    
                    summary += f"- **{component}**: {product}\n"
                    if cost:
                        summary += f"  - 月間コスト: {cost}円\n"
                    if issues:
                        summary += f"  - 課題: {', '.join(issues)}\n"
                    if details:
                        summary += f"  - 詳細情報: {details}\n"
                    
                    included_components.add(component)
        
        # Check for any components that weren't included
        if all_components - included_components:
            missing = list(all_components - included_components)
            summary += f"\n**注意: 次のコンポーネントについては情報が不完全です: {', '.join(missing)}**\n"
        
        # Add project information - 改善版
        project_section = "\n### プロジェクト情報\n"
        
        # 1. 予算情報
        budget = project_data.get('budget', '未定')
        project_section += f"- **予算**: {budget}\n"
        
        # 2. 最終意思決定者の情報 - 構造化
        if project_data.get('authority_option') == "どなたか別の方のご意向にも影響を受ける" and project_data.get('authority_position') and project_data.get('authority_name'):
            project_section += f"- **最終意思決定者**: 別の方の影響あり\n"
            project_section += f"  - 役職: {project_data.get('authority_position', '不明')}\n"
            project_section += f"  - 氏名: {project_data.get('authority_name', '不明')}\n"
        else:
            project_section += f"- **最終意思決定者**: {project_data.get('authority', '未定')}\n"
        
        # 3. 課題（ニーズ）
        need = project_data.get('need', '未定')
        if need:
            project_section += f"- **課題（ニーズ）**: {need}\n"
        
        # 4. 比較製品の情報 - リスト形式
        if project_data.get('competition_option') == "すでに他のサービスを比較予定 or 今後比較する予定がある" and project_data.get('competition_products'):
            project_section += f"- **比較製品**:\n"
            for product in project_data.get('competition_products', []):
                if product:  # 空の項目はスキップ
                    project_section += f"  - {product}\n"
        else:
            project_section += f"- **比較状況**: {project_data.get('competition', '未定')}\n"
        
        # 5. 選定基準
        criteria = project_data.get('decision_criteria', '未定')
        project_section += f"- **選定基準**: {criteria}\n"
        
        # 6. 意思決定プロセス
        process = project_data.get('decision_process', '未定')
        project_section += f"- **意思決定プロセス**: {process}\n"
        
        # 7. 導入時期（スケジュール）- タイムライン形式
        if project_data.get('timeframe_option') == "データ基盤構築・移行の具体的なスケジュールがある" and project_data.get('timeline_events'):
            project_section += f"- **導入スケジュール**:\n"
            
            # タイムラインイベントを日付でソート
            events = project_data.get('timeline_events', [])
            valid_events = [e for e in events if e.get('event')]  # イベント内容がある項目のみ
            
            # 月でソート
            sorted_events = sorted(valid_events, key=lambda x: int(x.get('month', '1')))
            
            # 時期の順序マッピング
            timing_order = {"初旬": 0, "中旬": 1, "下旬": 2}
            
            # 同じ月内で時期でソート
            from itertools import groupby
            for month, month_events in groupby(sorted_events, key=lambda x: x.get('month')):
                month_events_sorted = sorted(list(month_events), key=lambda x: timing_order.get(x.get('timing', '初旬'), 0))
                for event in month_events_sorted:
                    project_section += f"  - {event.get('month', '')}月{event.get('timing', '')}: {event.get('event', '')}\n"
        else:
            project_section += f"- **導入時期**: {project_data.get('timeframe', '未定')}\n"
        
        # 8. 商談情報補足
        additional_info = project_data.get('additional_info')
        if additional_info:
            project_section += f"- **補足情報**: {additional_info}\n"
        
        summary += project_section
        
        # Add next actions
        summary += f"""
### 次のアクション
{', '.join(next_actions) if next_actions else '未定'}
"""

        # Generate Databricks recommendations based on components found
        summary += f"""
### Databricks役立つ機能の仮説
現在の技術スタックおよび課題を考慮すると、以下のDatabricks機能が特に有効と考えられます：
"""

        # Add relevant recommendations based on components
        recommendations = []
        if "データカタログ" in all_components:
            recommendations.append("**Unity Catalog** - データガバナンスと統合されたセキュリティにより、データ検出とアクセス制御を強化します。")
        
        if "ジョブ管理" in all_components:
            recommendations.append("**Databricks Workflows** - ジョブ管理を効率化し、複雑なデータパイプラインを簡単に構築・管理できます。")
        
        if "データウェアハウス" in all_components:
            recommendations.append("**Databricks SQL** - 高速なクエリパフォーマンスを提供し、現在のデータウェアハウスやBIツールからの移行を容易にします。")
        
        if "ストレージ" in all_components:
            recommendations.append("**Delta Lake** - オープンソースのストレージレイヤーでACIDトランザクションをサポートし、データの信頼性と整合性を確保します。")
        
        if "AIプラットフォーム" in all_components or "生成AI" in all_components:
            recommendations.append("**Mosaic AI** - 大規模言語モデルの開発・デプロイ・管理を簡素化し、AIワークロードを効率化します。")
        
        if "データ変換" in all_components or "データ取り込み" in all_components:
            recommendations.append("**Delta Live Tables** - 宣言的なパイプライン構築で、データ品質チェックを含む堅牢なデータパイプラインを構築できます。")
            
        # Always include the Lakehouse Platform recommendation
        recommendations.append("**Databricks Lakehouse Platform** - データレイクとデータウェアハウスの統合により、データサイロを排除し、分析と機械学習のためのデータ準備を効率化します。")
        
        # Add numbered recommendations
        for i, rec in enumerate(recommendations, 1):
            summary += f"\n{i}. {rec}"
        
        return summary
    
    def _generate_databricks_points(self, component, issues):
        """Generate points where Databricks can contribute to solving the issues"""
        # 基本的な貢献ポイントを取得
        base_points = DATABRICKS_CONTRIBUTIONS.get(
            component, 
            "- **Databricks Lakehouse Platform**: データレイクとデータウェアハウスの統合により、データの一元管理と効率的な処理を実現"
        )
        
        # 課題固有の貢献ポイントを追加
        issue_specific_points = ""
        if issues:
            for issue in issues:
                if issue in ISSUE_SPECIFIC_CONTRIBUTIONS:
                    issue_specific_points += ISSUE_SPECIFIC_CONTRIBUTIONS[issue] + "\n"
        
        if issue_specific_points:
            return base_points + "\n\n### 課題に対する特定の貢献ポイント\n" + issue_specific_points
        return base_points

# Streamlit UI Components
class MigrationToolUI:
    def __init__(self, ai_service, state_manager, delta_manager):
        self.ai_service = ai_service
        if 'state_manager' not in st.session_state:
            st.session_state.state_manager = StateManager()
        self.state_manager = st.session_state.state_manager
        self.delta_manager = delta_manager
        self._setup_sidebar()
        
    # _setup_sidebar メソッドの変更
    def _setup_sidebar(self):
        """Setup the sidebar navigation"""
        with st.sidebar:
            st.title("DiscoveryDojo")
            st.subheader("ナビゲーション")
            
            # Initialize session state for navigation
            if 'nav' not in st.session_state:
                st.session_state.nav = {
                    'history_selection': True,
                    'customer_info': False,
                    'platform_discovery': False,
                    'project_data': False,
                    'next_actions': False,
                    'summary': False
                }
            
            # Navigation buttons
            if st.button("📋 履歴一覧"):
                self._show_section('history_selection')
            
            if st.button("🏢 顧客基本情報"):
                self._show_section('customer_info')
            
            if st.button("🔍 プラットフォーム調査"):
                self._show_section('platform_discovery')
            
            if st.button("📊 プロジェクト詳細"):
                self._show_section('project_data')
            
            if st.button("➡️ Next Action"):
                self._show_section('next_actions')
            
            if st.button("📝 まとめ"):
                self._show_section('summary')
            
            st.divider()
            
            # 編集中の場合、履歴IDを表示
            if 'editing_history' in st.session_state and st.session_state.editing_history:
                state_id = self.state_manager.get_id()
                if state_id:
                    st.caption(f"編集中のID: {state_id}")
            
            st.caption("© shotkotani")
    
    def _show_section(self, section):
        """Update session state to show the selected section"""
        for key in st.session_state.nav:
            st.session_state.nav[key] = (key == section)
        st.session_state.current_section = section
    
    def render_back_button(self, previous_section):
        """Render a back button to return to the previous section"""
        if st.button("← 前のステップに戻る"):
            self._show_section(previous_section)
            st.rerun()

    def render_history_selection(self):
        """Render the history selection screen"""
        st.title("DiscoveryDojo")
        st.header("ヒアリング履歴")
        
        # Delta Managerがない場合や接続できない場合
        if not hasattr(self, 'delta_manager') or not self.delta_manager.connection:
            st.warning("Delta Tableに接続できないため、履歴機能は利用できません。")
            
            # 新規ヒアリングボタンのみ表示
            if st.button("新規ヒアリングを開始", key="start_new_survey"):
                # Reset state manager
                self.state_manager.initialize()
                # Navigate to customer info section
                st.session_state.current_section = 'customer_info'
                st.session_state.editing_history = False
                st.rerun()
            return
            
        # Get history list
        history = self.delta_manager.get_history_list()
        
        if not history:
            st.info("履歴がありません。新規ヒアリングを開始してください。")
        else:
            st.success(f"{len(history)}件のヒアリング履歴があります。")
            
            # Display each history item as a card
            for item in history:
                with st.container():
                    col1, col2 = st.columns([3, 1])
                    
                    with col1:
                        st.markdown(f"""
                        <div class="history-card">
                            <div class="history-title">{item['company']}</div>
                            <div class="history-meta">
                                記録日: {item['record_date']} | 
                                記録者: {item['recorder']}
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    with col2:
                        if st.button("編集", key=f"edit_{item['id']}"):
                            # Load state from history
                            state = self.delta_manager.get_state_by_id(item['id'])
                            if state:
                                # Set state in state manager
                                self.state_manager.set_state(state)
                                # Navigate to customer info section
                                st.session_state.current_section = state.get("current_step", "customer_info")
                                st.session_state.editing_history = True
                                st.rerun()
                        
                        if st.button("削除", key=f"delete_{item['id']}"):
                            # Confirm deletion
                            if self.delta_manager.delete_history(item['id']):
                                st.success("履歴を削除しました。")
                                st.rerun()
        
        # New survey button
        if st.button("新規ヒアリングを開始", key="start_new_survey"):
            # Reset state manager
            self.state_manager.initialize()
            # Navigate to customer info section
            st.session_state.current_section = 'customer_info'
            st.session_state.editing_history = False
            st.rerun()

    def render_customer_info_section(self):
        """Render the customer basic information section"""
        st.header("顧客基本情報の登録")
        
        # 現在のステートから既存の値を取得
        state = self.state_manager.get_state()
        current_customer_info = state.get("customer_info", {})
        
        with st.form("customer_info_form"):
            col1, col2 = st.columns(2)
            
            with col1:
                # 既存の値をデフォルト値として設定
                company = st.text_input("社名", value=current_customer_info.get("company", ""))
                department = st.text_input("部署", value=current_customer_info.get("department", ""))
                person = st.text_input("お客様氏名", value=current_customer_info.get("person", ""))
                writer = st.text_input("記入者", value=current_customer_info.get("person", ""))
                
            with col2:
                # 日付入力を追加
                default_date = current_customer_info.get("meeting_date", datetime.now().strftime("%Y-%m-%d"))
                meeting_date = st.date_input("面談日", 
                                           value=datetime.strptime(default_date, "%Y-%m-%d") if isinstance(default_date, str) else datetime.now())
            
                persona = st.selectbox("ペルソナ", options=PERSONA_OPTIONS, 
                                    index=PERSONA_OPTIONS.index(current_customer_info.get("persona", PERSONA_OPTIONS[0])) 
                                    if current_customer_info.get("persona") in PERSONA_OPTIONS else 0)
                interest = st.selectbox("関心領域", options=INTEREST_OPTIONS, 
                                        index=INTEREST_OPTIONS.index(current_customer_info.get("interest", INTEREST_OPTIONS[0]))
                                        if current_customer_info.get("interest") in INTEREST_OPTIONS else 0)
            
            submit = st.form_submit_button("登録して次へ")
            
            if submit:
                if not company:
                    st.error("社名を入力してください")
                    return
                
                # 入力値をdict形式で保存
                customer_info = {
                    "company": company,
                    "department": department,
                    "person": person,
                    "writer": writer,
                    "meeting_date": meeting_date.strftime("%Y-%m-%d"),
                    "persona": persona,
                    "interest": interest
                }

                # ステートマネージャーを更新
                self.state_manager.update_customer_info(customer_info)
                
                # ナビゲーションを更新
                st.session_state.nav['platform_discovery'] = True
                self._show_section('platform_discovery')
                st.rerun()

                # 編集モード時は状態を保存
                if 'editing_history' in st.session_state and st.session_state.editing_history:
                    state_id = self.state_manager.get_id()
                    if state_id:
                        self.delta_manager.save_state(self.state_manager.get_state())
                
    def render_platform_discovery_section(self):
        """Render the platform discovery section with cloud tabs"""
        # Hide sidebar for this section using CSS
        st.markdown("""
        <style>
        [data-testid="stSidebar"] {
            display: none;
        }
        .main .block-container {
            max-width: 100%;
            padding-left: 2rem;
            padding-right: 2rem;
        }
        </style>
        """, unsafe_allow_html=True)
        
        st.header("プラットフォーム調査")
        
        # Add a button to navigate back to customer info
        if st.button("← 顧客情報に戻る", key="back_to_customer_info"):
            # Show sidebar again when navigating away
            st.markdown("""
            <style>
            [data-testid="stSidebar"] {
                display: block;
            }
            </style>
            """, unsafe_allow_html=True)
            self._show_section('customer_info')
            st.rerun()
        
        # Get state
        state = self.state_manager.get_state()
        current_cloud = state.get("current_cloud", "AWS")
        
        # Initialize platform discovery session state if not exists
        if 'platform_discovery' not in st.session_state:
            st.session_state.platform_discovery = {
                'selected_components': {},
                'highlighted_components': [],
                'selected_cloud': current_cloud
            }
        
        # Get customer persona
        customer_persona = state.get("customer_info", {}).get("persona", "")
        
        # Update highlighted components based on persona
        if customer_persona and customer_persona in PERSONA_STACK_MAPPING:
            st.session_state.platform_discovery['highlighted_components'] = PERSONA_STACK_MAPPING[customer_persona]
        
        # Cloud tabs
        cloud_tabs = st.tabs(CLOUD_OPTIONS)
        
        for i, cloud in enumerate(CLOUD_OPTIONS):
            with cloud_tabs[i]:
                self._render_cloud_platform_content(cloud, customer_persona)
        
        # Button to proceed to project data
        col1, col2, col3 = st.columns([1, 1, 1])
        with col2:
            if st.button("プラットフォーム調査を完了してプロジェクト詳細へ進む", key="complete_platform"):
                # Show sidebar again when navigating away
                st.markdown("""
                <style>
                [data-testid="stSidebar"] {
                    display: block;
                }
                .main .block-container {
                    max-width: 80rem;
                    padding-left: 5rem;
                    padding-right: 5rem;
                }
                </style>
                """, unsafe_allow_html=True)
                self.state_manager.move_to_project_data()
                st.session_state.nav['project_data'] = True
                self._show_section('project_data')
                st.rerun()

                # 編集モード時は状態を保存
                if 'editing_history' in st.session_state and st.session_state.editing_history:
                    state_id = self.state_manager.get_id()
                    if state_id:
                        self.delta_manager.save_state(self.state_manager.get_state())
    
    def _render_cloud_platform_content(self, cloud, customer_persona):
        """Render the platform content for a specific cloud"""
        state = self.state_manager.get_state()
        
        # Get platform data for this cloud
        platform_data = state.get("platform_data", {}).get(cloud, [])
        
        # Update current cloud in state
        state["current_cloud"] = cloud
        
        # Initialize selected component in session state if not exists
        if 'platform_selected_component' not in st.session_state:
            st.session_state.platform_selected_component = {}
        if cloud not in st.session_state.platform_selected_component:
            st.session_state.platform_selected_component[cloud] = None
            
        # Initialize temporary form data in session state
        if 'temp_form_data' not in st.session_state:
            st.session_state.temp_form_data = {}
        key = f"{cloud}_form_data"
        if key not in st.session_state.temp_form_data:
            st.session_state.temp_form_data[key] = {}
            
        # Create two columns: one for stack visualization, one for details
        col1, col2 = st.columns([4, 3])
        
        # Create containers for two main sections to allow partial updates
        with col1:
            stack_container = st.container()
        
        with col2:
            detail_container = st.container()
            
        deepdive_container = st.container()
        
        # Function to save component data without page refresh
        def save_component_data(component, product, cost, issues, details):
            # Find existing data for this component
            existing_data = None
            for item in platform_data:
                if item.get("component") == component:
                    existing_data = item
                    break
                    
            # Create or update component data
            component_data = {
                "component": component,
                "product": product,
                "cost": cost,
                "issues": issues,
                "details": details
            }
            
            # Update platform data
            new_platform_data = [item for item in platform_data if item.get("component") != component]
            new_platform_data.append(component_data)
            
            # Update state without triggering rerun
            self.state_manager.update_platform_data(new_platform_data, cloud)
            
            # Return success message
            return f"✅ {component}の情報を保存しました"
            
        # Render stack visualization section
        with stack_container:
            st.subheader(f"{cloud}の現在のデータスタック")
            
            # Render categories and components
            for category, components in DATA_STACK.items():
                # Create row with category label and components
                # Adjust column widths to give more space for buttons
                cols = st.columns([1.2] + [1] * len(components))
                
                # Display category name in first column
                with cols[0]:
                    st.markdown(f"<div class='category-label' style='font-weight: bold;'>{category}</div>", unsafe_allow_html=True)
                
                # Display component buttons in remaining columns
                for i, component in enumerate(components):
                    with cols[i+1]:  # +1 because first column is for category name
                        # Format longer names with line breaks if needed
                        display_name = component
                        if len(component) > 10 and "ウェアハウス" in component:
                            display_name = component.replace("ウェアハウス", "<br>ハウス")
                        elif len(component) > 10 and "プラットフォーム" in component:
                            display_name = component.replace("プラットフォーム", "<br>フォーム")
                        
                        # Check if component should be highlighted based on persona
                        is_highlighted = component in st.session_state.platform_discovery.get('highlighted_components', [])
                        
                        # Check if component is selected
                        is_selected = False
                        for item in platform_data:
                            if item.get("component") == component:
                                is_selected = True
                                break
                                
                        # Check if this is the currently selected component
                        is_active = st.session_state.platform_selected_component.get(cloud) == component
                        
                        # Add visual indicators for status
                        status_indicator = ""
                        if is_highlighted and not is_active:
                            status_indicator = "🔸 "  # Orange diamond for highlighted
                        if is_selected and not is_active:
                            status_indicator = "✅ "  # Green check for selected
                        
                        # Create button with different styling based on status
                        button_text = f"{status_indicator}{display_name}"
                        if "<br>" in display_name:
                            button_text = f"{status_indicator}{display_name.replace('<br>', ' ')}"

                        # 一貫したスタイリングのためのボタンHTML
                        # HTMLを直接使用してボタンを作成する代わりに、st.buttonを使用して後でCSSで装飾
                        if st.button(button_text, key=f"btn_{cloud}_{component}"):
                            st.session_state.platform_selected_component[cloud] = component
                            # Initialize form data for this component if it doesn't exist
                            form_key = f"{cloud}_{component}"
                            if form_key not in st.session_state.temp_form_data[key]:
                                # Find existing data for this component
                                existing_data = None
                                for item in platform_data:
                                    if item.get("component") == component:
                                        existing_data = item
                                        break
                                
                                if existing_data:
                                    st.session_state.temp_form_data[key][form_key] = {
                                        "product": existing_data.get("product", ""),
                                        "cost": existing_data.get("cost", ""),
                                        "issues": existing_data.get("issues", []),
                                        "details": existing_data.get("details", "")
                                    }
                                else:
                                    # Get available products for this component and cloud
                                    available_products = PRODUCTS_BY_CLOUD.get(cloud, {}).get(component, [])
                                    default_product = available_products[0] if available_products else ""
                                    st.session_state.temp_form_data[key][form_key] = {
                                        "product": default_product,
                                        "cost": "",
                                        "issues": [],
                                        "details": ""
                                    }
                                    
                        # ボタンのスタイルを適用（JavaScriptを使用）
                        if is_active:
                            st.markdown(f"""
                            <script>
                                document.querySelector('button[kind="secondary"][data-testid="stButton"][aria-label="{button_text}"]').className += " button-active";
                            </script>
                            """, unsafe_allow_html=True)
                        elif is_highlighted:
                            st.markdown(f"""
                            <script>
                                document.querySelector('button[kind="secondary"][data-testid="stButton"][aria-label="{button_text}"]').className += " button-highlight";
                            </script>
                            """, unsafe_allow_html=True)
                        elif is_selected:
                            st.markdown(f"""
                            <script>
                                document.querySelector('button[kind="secondary"][data-testid="stButton"][aria-label="{button_text}"]').className += " button-completed";
                            </script>
                            """, unsafe_allow_html=True)
                            
                            # No need to rerun the entire page - let the UI update naturally
                
                # Add some spacing between categories
                st.markdown("<div style='margin-bottom: 20px;'></div>", unsafe_allow_html=True)
        
        # Render component details section
        with detail_container:
            # Get selected component from session state
            selected_component = st.session_state.platform_selected_component.get(cloud)
            
            # 動的なタイトルを表示（コンポーネントが選択されている場合）
            if selected_component:
                st.subheader(f"{selected_component}の詳細")
                
                # Form key for the selected component
                form_key = f"{cloud}_{selected_component}"
                
                # Find existing data for this component
                existing_data = None
                for item in platform_data:
                    if item.get("component") == selected_component:
                        existing_data = item
                        break
                
                # Get available products for this component and cloud
                available_products = PRODUCTS_BY_CLOUD.get(cloud, {}).get(selected_component, [])
                
                # Create a form-like interface but without using st.form to avoid full page rerunning
                col1, col2 = st.columns(2)
                
                with col1:
                    # Product selection
                    product_index = 0
                    if form_key in st.session_state.temp_form_data[key]:
                        product = st.session_state.temp_form_data[key][form_key].get("product", "")
                        if product in available_products:
                            product_index = available_products.index(product)
                    
                    selected_product = st.selectbox(
                        "使用中の製品",
                        options=available_products,
                        index=product_index,
                        key=f"product_{form_key}"
                    )
                    if form_key in st.session_state.temp_form_data[key]:
                        st.session_state.temp_form_data[key][form_key]["product"] = selected_product
                
                with col2:
                    # Cost input
                    default_cost = ""
                    if form_key in st.session_state.temp_form_data[key]:
                        default_cost = st.session_state.temp_form_data[key][form_key].get("cost", "")
                    
                    cost = st.text_input(
                        "月間コスト（円）",
                        value=default_cost,
                        key=f"cost_{form_key}"
                    )
                    if form_key in st.session_state.temp_form_data[key]:
                        st.session_state.temp_form_data[key][form_key]["cost"] = cost
                
                # Common issues multiselect
                common_issues = COMMON_ISSUES.get(selected_component, [])
                default_issues = []
                if form_key in st.session_state.temp_form_data[key]:
                    default_issues = st.session_state.temp_form_data[key][form_key].get("issues", [])
                
                selected_issues = st.multiselect(
                    "現在の課題",
                    options=common_issues,
                    default=default_issues,
                    key=f"issues_{form_key}"
                )
                if form_key in st.session_state.temp_form_data[key]:
                    st.session_state.temp_form_data[key][form_key]["issues"] = selected_issues
                
                # Details input
                default_details = ""
                if form_key in st.session_state.temp_form_data[key]:
                    default_details = st.session_state.temp_form_data[key][form_key].get("details", "")
                
                details = st.text_area(
                    "詳細情報",
                    value=default_details,
                    height=100,
                    key=f"details_{form_key}"
                )
                if form_key in st.session_state.temp_form_data[key]:
                    st.session_state.temp_form_data[key][form_key]["details"] = details
                
                # Save button
                if st.button("保存", key=f"save_{form_key}"):
                    # Get data from session state
                    if form_key in st.session_state.temp_form_data[key]:
                        form_data = st.session_state.temp_form_data[key][form_key]
                        result = save_component_data(
                            selected_component,
                            form_data.get("product", ""),
                            form_data.get("cost", ""),
                            form_data.get("issues", []),
                            form_data.get("details", "")
                        )
                        st.success(result)
            else:
                # コンポーネントが選択されていない場合のメッセージ
                st.subheader("コンポーネントを選択してください")
        
        # Display the deep-dive section and Databricks points outside of the columns, using full width
        selected_component = st.session_state.platform_selected_component.get(cloud)
        if selected_component:
            # Find existing data for this component
            existing_data = None
            for item in platform_data:
                if item.get("component") == selected_component:
                    existing_data = item
                    break
                    
            with deepdive_container:
                st.markdown("---")
                st.markdown(f"## {selected_component}の詳細分析")
                
                st.markdown("### 深掘り質問")
                # Generate deep dive question based on component and issues
                if existing_data and "issues" in existing_data:
                    question = self.ai_service.generate_deep_dive_question(selected_component, existing_data.get("issues", []))
                else:
                    question = self.ai_service.generate_deep_dive_question(selected_component, [])
                
                st.info(question)
                
                # Generate Databricks contribution points
                st.markdown("### Databricksの貢献ポイント")
                databricks_points = self.ai_service._generate_databricks_points(selected_component, existing_data.get("issues", []) if existing_data else [])
                st.success(databricks_points)
    
    def render_project_data_section(self):
        """Render the project information section"""
        st.header("プロジェクト情報確認")
        
        # Add back button
        self.render_back_button('platform_discovery')
        
        # Get state
        state = self.state_manager.get_state()
        
        # Initialize unified project data
        project_data = state.get("project_data", {})
        
        # 比較製品の追加・削除のためのセッション状態を初期化
        # フォーム外で操作するためのステート
        if 'comparison_products_count' not in st.session_state:
            if "competition_products" in project_data and isinstance(project_data["competition_products"], list):
                st.session_state.comparison_products_count = len(project_data["competition_products"])
            else:
                st.session_state.comparison_products_count = 1
        
        # フォーム外での比較製品の追加・削除コントロール
        if "competition_option" in project_data and project_data["competition_option"] == "すでに他のサービスを比較予定 or 今後比較する予定がある":
            st.subheader("比較製品の追加・削除")
            col1, col2 = st.columns([3, 1])
            with col1:
                st.info("下記のフォームで比較製品の詳細を入力してください。現在の製品数: " + str(st.session_state.comparison_products_count))
            with col2:
                # Add button
                if st.button("比較製品を追加", key="add_comparison_product_outside"):
                    st.session_state.comparison_products_count += 1
                    # 製品リストを更新
                    if "competition_products" not in project_data:
                        project_data["competition_products"] = [""] * st.session_state.comparison_products_count
                    else:
                        project_data["competition_products"].append("")
                    st.experimental_rerun()
                
                # Remove button (only show if there's more than one product)
                if st.session_state.comparison_products_count > 1:
                    if st.button("最後の製品を削除", key="remove_comparison_product_outside"):
                        st.session_state.comparison_products_count -= 1
                        # 製品リストを更新
                        if "competition_products" in project_data and len(project_data["competition_products"]) > 0:
                            project_data["competition_products"].pop()
                        st.experimental_rerun()
        
        # メインのフォーム
        with st.form("combined_form"):
            st.subheader("商談情報")
            
            # プロジェクト予算
            st.markdown("### プロジェクト実施の予算の有無")
            budget_options = [
                "検証のためのソフトウェアやサービス実装のための予算を確保済",
                "近々予算を申請予定 (必要な予算を知りたい)",
                "コスト低減が可能であれば既存サービスに支払っている費用を回すことが可能",
                "予算はなく、申請予定もない",
                "その他"
            ]
            
            budget_selection = st.selectbox(
                "予算状況",
                options=budget_options,
                index=budget_options.index(project_data.get("budget_option", budget_options[0])) if "budget_option" in project_data else 0
            )
            
            if budget_selection == "その他":
                budget_other = st.text_area(
                    "詳細を入力してください",
                    value=project_data.get("budget_detail", "")
                )
                project_data["budget_detail"] = budget_other
            
            project_data["budget_option"] = budget_selection
            project_data["budget"] = budget_selection if budget_selection != "その他" else f"その他: {project_data.get('budget_detail', '')}"
            
            # 最終意思決定者
            st.markdown("### 最終意思決定者")
            decision_maker_options = [
                "ご自身で利用するソフトウェアを決めることが可能",
                "どなたか別の方のご意向にも影響を受ける",
            ]
            
            decision_maker = st.selectbox(
                "決裁権",
                options=decision_maker_options,
                index=decision_maker_options.index(project_data.get("authority_option", decision_maker_options[0])) if "authority_option" in project_data else 0
            )
            
            if decision_maker == "どなたか別の方のご意向にも影響を受ける":
                col1, col2 = st.columns(2)
                with col1:
                    authority_position = st.text_input(
                        "意思決定者の役職",
                        value=project_data.get("authority_position", "")
                    )
                    project_data["authority_position"] = authority_position
                
                with col2:
                    authority_name = st.text_input(
                        "意思決定者のお名前",
                        value=project_data.get("authority_name", "")
                    )
                    project_data["authority_name"] = authority_name
                
                project_data["authority_detail"] = f"役職: {authority_position}, 名前: {authority_name}"
            
            project_data["authority_option"] = decision_maker
            project_data["authority"] = decision_maker if decision_maker != "どなたか別の方のご意向にも影響を受ける" else f"どなたか別の方のご意向: {project_data.get('authority_detail', '')}"
            
            # 課題（ニーズ）
            st.markdown("### 課題（ニーズ）")
            need = st.text_area(
                "なぜこの製品/サービスが必要ですか？",
                value=project_data.get("need", ""),
                help="例: 現在のデータ処理に時間がかかりすぎている"
            )
            project_data["need"] = need
            
            # 比較製品
            st.markdown("### 比較製品")
            comparison_options = [
                "他のサービスを比較予定はない",
                "すでに他のサービスを比較予定 or 今後比較する予定がある",
                "そもそも比較すべきサービスがわからない"
            ]
            
            comparison = st.selectbox(
                "比較状況",
                options=comparison_options,
                index=comparison_options.index(project_data.get("competition_option", comparison_options[0])) if "competition_option" in project_data else 0
            )
            
            if comparison == "すでに他のサービスを比較予定 or 今後比較する予定がある":
                # 初期化
                if "competition_products" not in project_data:
                    project_data["competition_products"] = [""] * st.session_state.comparison_products_count
                
                # 製品リストの長さがセッション状態と一致するように調整
                while len(project_data["competition_products"]) < st.session_state.comparison_products_count:
                    project_data["competition_products"].append("")
                while len(project_data["competition_products"]) > st.session_state.comparison_products_count:
                    project_data["competition_products"].pop()
                
                # 製品リストを表示 (フォーム内なのでボタンなし)
                for i, product in enumerate(project_data["competition_products"]):
                    product_input = st.text_input(
                        f"比較対象製品 {i+1}",
                        value=product,
                        key=f"competition_product_{i}"
                    )
                    project_data["competition_products"][i] = product_input
                
                # 比較製品リストを文字列に変換
                competition_detail = ", ".join([p for p in project_data["competition_products"] if p])
                project_data["competition_detail"] = competition_detail
            
            project_data["competition_option"] = comparison
            project_data["competition"] = comparison if comparison != "すでに他のサービスを比較予定 or 今後比較する予定がある" else f"比較予定: {project_data.get('competition_detail', '')}"
            
            # サービス選定の基準
            st.markdown("### サービス選定の基準（複数選択可）")
            criteria_options = [
                "コスト",
                "パフォーマンス",
                "UI/UX",
                "既存スキルとの親和性",
                "既存環境との親和性",
                "セキュリティ"
            ]
            
            selected_criteria = st.multiselect(
                "選定基準",
                options=criteria_options,
                default=project_data.get("decision_criteria_selected", [])
            )
            
            project_data["decision_criteria_selected"] = selected_criteria
            project_data["decision_criteria"] = ", ".join(selected_criteria) if selected_criteria else "未指定"
            
            # 意思決定のプロセス
            st.markdown("### 意思決定のプロセス")
            process_options = [
                "RFPを実施予定",
                "PoCを実施予定",
                "机上検証を実施予定",
                "その他"
            ]
            
            process = st.selectbox(
                "プロセス",
                options=process_options,
                index=process_options.index(project_data.get("decision_process_option", process_options[0])) if "decision_process_option" in project_data else 0
            )
            
            if process == "その他":
                process_detail = st.text_area(
                    "詳細を入力してください",
                    value=project_data.get("decision_process_detail", "")
                )
                project_data["decision_process_detail"] = process_detail
            
            project_data["decision_process_option"] = process
            project_data["decision_process"] = process if process != "その他" else f"その他: {project_data.get('decision_process_detail', '')}"
            
            # スケジュール
            st.markdown("### スケジュール")
            schedule_options = [
                "データ基盤構築・移行の具体的なスケジュールがある",
                "具体的なスケジュールは現状ない"
            ]
            
            schedule = st.selectbox(
                "スケジュール状況",
                options=schedule_options,
                index=schedule_options.index(project_data.get("timeframe_option", schedule_options[0])) if "timeframe_option" in project_data else 0
            )
            
            if schedule == "データ基盤構築・移行の具体的なスケジュールがある":
                # 常に5つのイベントフォームを表示
                if "timeline_events" not in project_data:
                    # 初期化 - 5つの空のイベントを作成
                    project_data["timeline_events"] = [
                        {"month": "4", "timing": "初旬", "event": ""},
                        {"month": "5", "timing": "初旬", "event": ""},
                        {"month": "6", "timing": "初旬", "event": ""},
                        {"month": "7", "timing": "初旬", "event": ""},
                        {"month": "8", "timing": "初旬", "event": ""}
                    ]
                
                # リストが5つになるように調整
                while len(project_data["timeline_events"]) < 5:
                    project_data["timeline_events"].append({"month": "4", "timing": "初旬", "event": ""})
                
                # 最初の5つのイベントだけを使用
                project_data["timeline_events"] = project_data["timeline_events"][:5]
                
                # 5つのイベントフォームを表示
                st.info("以下のイベントフォームに入力してください（使用しない欄は空白のままで構いません）")
                
                for i, event in enumerate(project_data["timeline_events"]):
                    col1, col2, col3 = st.columns([2, 2, 5])
                    
                    with col1:
                        # 月選択
                        month_options = [str(m) for m in range(1, 13)]
                        month = st.selectbox(
                            "月",
                            options=month_options,
                            index=month_options.index(event.get("month", "4")) if event.get("month", "4") in month_options else 3,
                            key=f"month_{i}"
                        )
                        project_data["timeline_events"][i]["month"] = month
                    
                    with col2:
                        # 時期選択
                        timing_options = ["初旬", "中旬", "下旬"]
                        timing = st.selectbox(
                            "時期",
                            options=timing_options,
                            index=timing_options.index(event.get("timing", "初旬")) if event.get("timing", "初旬") in timing_options else 0,
                            key=f"timing_{i}"
                        )
                        project_data["timeline_events"][i]["timing"] = timing
                    
                    with col3:
                        # イベント内容
                        event_content = st.text_input(
                            "イベント内容",
                            value=event.get("event", ""),
                            key=f"event_{i}"
                        )
                        project_data["timeline_events"][i]["event"] = event_content
                
                # タイムラインを文字列に変換（空のイベントは除外）
                timeline_details = []
                for event in project_data["timeline_events"]:
                    if event["event"]:  # イベント内容が空でない場合のみ
                        timeline_details.append(f"{event['month']}月{event['timing']}: {event['event']}")
                
                timeframe_detail = ", ".join(timeline_details)
                project_data["timeframe_detail"] = timeframe_detail
            
            project_data["timeframe_option"] = schedule
            project_data["timeframe"] = schedule if schedule != "データ基盤構築・移行の具体的なスケジュールがある" else f"スケジュールあり: {project_data.get('timeframe_detail', '')}"
            
            # 商談情報の補足
            st.markdown("### 商談情報補足")
            additional_info = st.text_area(
                "その他、商談に関する補足情報があれば入力してください",
                value=project_data.get("additional_info", "")
            )
            project_data["additional_info"] = additional_info
            
            # Submit button
            submit = st.form_submit_button("保存して次へ")
            
            if submit:
                # 状態を更新
                self.state_manager.update_project_data(project_data)
                
                # 次のセクションへ
                st.session_state.nav['next_actions'] = True
                self._show_section('next_actions')
                st.rerun()

                # 編集モード時は状態を保存
                if 'editing_history' in st.session_state and st.session_state.editing_history:
                    state_id = self.state_manager.get_id()
                    if state_id:
                        self.delta_manager.save_state(self.state_manager.get_state())
                
    def render_next_actions_section(self):
        """Render the next actions section"""
        st.header("Next Action")
        
        # Add back button
        self.render_back_button('project_data')

        # Get state
        state = self.state_manager.get_state()
        
        with st.form("next_actions_form"):
            selected_actions = st.multiselect(
                "次のアクションを選択してください",
                options=NEXT_ACTION_OPTIONS,
                default=state.get("next_actions", [])
            )
            
            submit = st.form_submit_button("保存して次へ")
            
            if submit:
                # Update state
                self.state_manager.update_next_actions(selected_actions)
                
                # Enable next section
                st.session_state.nav['summary'] = True
                self._show_section('summary')
                st.rerun()

                # 編集モード時は状態を保存
                if 'editing_history' in st.session_state and st.session_state.editing_history:
                    state_id = self.state_manager.get_id()
                    if state_id:
                        self.delta_manager.save_state(self.state_manager.get_state())
    
    def render_summary_section(self):
        """Render the summary section"""
        st.header("ヒアリングした結果のまとめ")

        # Add back button
        self.render_back_button('next_actions')
        
        # Get state
        state = self.state_manager.get_state()
        
        # Always regenerate summary to ensure it has the latest data
        with st.spinner("結果のまとめを生成中..."):
            summary = self.ai_service.generate_summary(state)
            st.session_state.summary = summary
        
        # Display summary
        st.markdown("### 結果まとめ")
        st.markdown(st.session_state.summary)
        
        # Display debug information in an expander for troubleshooting
        with st.expander("デバッグ情報", expanded=False):
            st.write("### State Data:")
            st.json(state)
        
        # Export options
        st.subheader("エクスポート")
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("テキストとしてコピー"):
                st.code(st.session_state.summary)
                st.success("上記のテキストをコピーしてください")
        
        with col2:
            if st.button("新しいヒアリングを開始"):
                # Reset all session state
                for key in list(st.session_state.keys()):
                    if key != 'state_manager':
                        del st.session_state[key]
                
                # Initialize state
                self.state_manager.initialize()
                
                # Show customer info section
                self._show_section('customer_info')
                st.rerun()

        # Save to Delta table
        if st.button("ヒアリング結果を保存", key="save_to_delta"):
            with st.spinner("データを保存中..."):
                state_id = self.delta_manager.save_state(state)
                if state_id:
                    self.state_manager.set_id(state_id)
                    st.success(f"ヒアリング結果を保存しました。ID: {state_id}")
                else:
                    st.error("保存に失敗しました。")

def main():
    # Initialize components
    ai_service = AIModelService()
    
    # Delta Managerの初期化を試みる
    try:
        delta_manager = DeltaTableManager(CONFIG)
    except Exception as e:
        st.error(f"Delta Table管理の初期化エラー: {e}")
        delta_manager = None
    
    # Initialize state manager if not exists
    if 'state_manager' not in st.session_state:
        st.session_state.state_manager = StateManager()
    
    # Initialize UI
    ui = MigrationToolUI(ai_service, st.session_state.state_manager, delta_manager)
    
    # 履歴モードが失敗した場合のフォールバック
    if not hasattr(ui, 'delta_manager') or not ui.delta_manager or not ui.delta_manager.connection:
        if 'current_section' not in st.session_state or st.session_state.current_section == 'history_selection':
            st.session_state.current_section = 'customer_info'
    
    # Initialize editing_history flag if not exists
    if 'editing_history' not in st.session_state:
        st.session_state.editing_history = False
    
    # Check if we need to reset sidebar visibility
    if 'current_section' in st.session_state:
        current_section = st.session_state.current_section
        if current_section != 'platform_discovery':
            # Ensure sidebar is shown for non-platform-discovery sections
            st.markdown("""
            <style>
            [data-testid="stSidebar"] {
                display: block;
            }
            .main .block-container {
                max-width: 80rem;
                padding-left: 5rem;
                padding-right: 5rem;
            }
            </style>
            """, unsafe_allow_html=True)
    
    # Initialize session state for current section if not already initialized
    if 'current_section' not in st.session_state:
        # 接続できない場合はhistory_selectionをスキップする
        if delta_manager and delta_manager.connection:
            st.session_state.current_section = 'history_selection'
        else:
            st.session_state.current_section = 'customer_info'
    
    # Render current section
    current_section = st.session_state.current_section
    
    if current_section == 'history_selection':
        if hasattr(ui, 'render_history_selection'):
            ui.render_history_selection()
        else:
            st.session_state.current_section = 'customer_info'
            st.rerun()
    elif current_section == 'customer_info':
        ui.render_customer_info_section()
    elif current_section == 'platform_discovery':
        ui.render_platform_discovery_section()
    elif current_section == 'project_data':
        ui.render_project_data_section()
    elif current_section == 'next_actions':
        ui.render_next_actions_section()
    elif current_section == 'summary':
        ui.render_summary_section()
        
if __name__ == "__main__":
    main()