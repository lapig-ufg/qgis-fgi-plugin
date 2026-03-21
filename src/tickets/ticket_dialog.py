# -*- coding: utf-8 -*-
import os
import tempfile
import uuid

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QPixmap, QFont, QColor
from qgis.PyQt.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .ticket_api import TicketApiClient, TicketApiError

# Credenciais fixas para autenticação do plugin
_CAMPAIGN = 'gpw-plugin'
_PASSWORD = 'gpw-plugin'

# Mapeamento de valores da API para rótulos legíveis
_TYPE_LABELS = {
    'RECLAMACAO': 'Reclamação',
    'SUGESTAO': 'Sugestão',
    'DUVIDA': 'Dúvida',
    'ELOGIO': 'Elogio',
}
_STATUS_LABELS = {
    'ABERTO': 'Aberto',
    'EM_ANALISE': 'Em análise',
    'EM_DESENVOLVIMENTO': 'Em desenvolvimento',
    'RESOLVIDO': 'Resolvido',
    'FECHADO': 'Fechado',
}
_STATUS_COLORS = {
    'ABERTO': '#2196F3',
    'EM_ANALISE': '#FF9800',
    'EM_DESENVOLVIMENTO': '#9C27B0',
    'RESOLVIDO': '#4CAF50',
    'FECHADO': '#757575',
}
_CATEGORY_LABELS = {
    'INTERFACE': 'Interface',
    'DESEMPENHO': 'Desempenho',
    'FUNCIONALIDADE': 'Funcionalidade',
    'DADOS': 'Dados',
    'OUTRO': 'Outro',
}
_SEVERITY_LABELS = {
    'BAIXA': 'Baixa',
    'MEDIA': 'Média',
    'ALTA': 'Alta',
    'CRITICA': 'Crítica',
}


class TicketDialog(QDialog):
    """Diálogo para registro e consulta de tickets no TVI."""

    TYPE_OPTIONS = [
        ('Reclamação', 'RECLAMACAO'),
        ('Sugestão', 'SUGESTAO'),
        ('Dúvida', 'DUVIDA'),
        ('Elogio', 'ELOGIO'),
    ]

    CATEGORY_OPTIONS = [
        ('Interface', 'INTERFACE'),
        ('Desempenho', 'DESEMPENHO'),
        ('Funcionalidade', 'FUNCIONALIDADE'),
        ('Dados', 'DADOS'),
        ('Outro', 'OUTRO'),
    ]

    SEVERITY_OPTIONS = [
        ('Baixa', 'BAIXA'),
        ('Média', 'MEDIA'),
        ('Alta', 'ALTA'),
        ('Crítica', 'CRITICA'),
    ]

    def __init__(self, iface, api_client, interpreter_name='', parent=None):
        super().__init__(parent)
        self.iface = iface
        self.api = api_client
        self._interpreter_name = interpreter_name.strip() if interpreter_name else ''
        self._attachment_path = None
        self._temp_file = None
        self._tickets_data = []
        self._current_page = 1
        self._total_pages = 1
        self._setup_ui()

    def _get_user_name(self):
        if self._interpreter_name:
            return self._interpreter_name
        return f'usuario-plugin-fgi-{uuid.uuid4().hex[:8]}'

    # =========================================================================
    # UI Setup
    # =========================================================================

    def _setup_ui(self):
        self.setWindowTitle('Tickets')
        self.setMinimumWidth(560)
        self.setMinimumHeight(580)

        main_layout = QVBoxLayout(self)

        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)

        # Aba 1 — Novo Ticket
        self.tab_new = QWidget()
        self._setup_new_ticket_tab()
        self.tab_widget.addTab(self.tab_new, 'Novo Ticket')

        # Aba 2 — Meus Tickets
        self.tab_list = QWidget()
        self._setup_list_tab()
        self.tab_widget.addTab(self.tab_list, 'Meus Tickets')

        self.tab_widget.currentChanged.connect(self._on_tab_changed)

    # --- Aba: Novo Ticket ---------------------------------------------------

    def _setup_new_ticket_tab(self):
        layout = QVBoxLayout(self.tab_new)

        form_layout = QFormLayout()

        self.title_edit = QLineEdit()
        self.title_edit.setMaxLength(200)
        self.title_edit.setPlaceholderText('Descreva brevemente o problema ou sugestão')
        form_layout.addRow('Título:', self.title_edit)

        self.type_combo = QComboBox()
        for label, value in self.TYPE_OPTIONS:
            self.type_combo.addItem(label, value)
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        form_layout.addRow('Tipo:', self.type_combo)

        self.category_combo = QComboBox()
        for label, value in self.CATEGORY_OPTIONS:
            self.category_combo.addItem(label, value)
        form_layout.addRow('Categoria:', self.category_combo)

        self.severity_label = QLabel('Severidade:')
        self.severity_combo = QComboBox()
        for label, value in self.SEVERITY_OPTIONS:
            self.severity_combo.addItem(label, value)
        form_layout.addRow(self.severity_label, self.severity_combo)

        self.description_edit = QPlainTextEdit()
        self.description_edit.setPlaceholderText(
            'Descreva o problema em detalhes: o que aconteceu, '
            'o que era esperado e como reproduzir.'
        )
        self.description_edit.setMinimumHeight(100)
        form_layout.addRow('Descrição:', self.description_edit)

        layout.addLayout(form_layout)

        # Captura de tela
        attachment_group = QGroupBox('Captura de tela (opcional)')
        attachment_layout = QVBoxLayout(attachment_group)

        btn_row = QHBoxLayout()
        self.btn_select_file = QPushButton('Selecionar arquivo...')
        self.btn_select_file.clicked.connect(self._select_file)
        btn_row.addWidget(self.btn_select_file)

        self.btn_capture_canvas = QPushButton('Capturar tela')
        self.btn_capture_canvas.clicked.connect(self._capture_canvas)
        btn_row.addWidget(self.btn_capture_canvas)

        self.btn_remove_attachment = QPushButton('Remover')
        self.btn_remove_attachment.clicked.connect(self._remove_attachment)
        self.btn_remove_attachment.hide()
        btn_row.addWidget(self.btn_remove_attachment)

        btn_row.addStretch()
        attachment_layout.addLayout(btn_row)

        preview_row = QHBoxLayout()
        self.preview_label = QLabel()
        self.preview_label.setFixedSize(160, 120)
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setStyleSheet(
            'border: 1px solid #ccc; background: #f5f5f5;'
        )
        preview_row.addWidget(self.preview_label)

        self.file_name_label = QLabel('')
        self.file_name_label.setWordWrap(True)
        self.file_name_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        preview_row.addWidget(self.file_name_label)

        attachment_layout.addLayout(preview_row)
        layout.addWidget(attachment_group)

        # Botões de ação
        action_layout = QHBoxLayout()
        action_layout.addStretch()

        self.btn_cancel = QPushButton('Cancelar')
        self.btn_cancel.clicked.connect(self.reject)
        action_layout.addWidget(self.btn_cancel)

        self.btn_submit = QPushButton('Enviar')
        self.btn_submit.setDefault(True)
        self.btn_submit.clicked.connect(self._submit)
        action_layout.addWidget(self.btn_submit)

        layout.addLayout(action_layout)

        self._on_type_changed()

    # --- Aba: Meus Tickets ---------------------------------------------------

    def _setup_list_tab(self):
        layout = QVBoxLayout(self.tab_list)

        # Filtro de status
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel('Status:'))
        self.filter_status = QComboBox()
        self.filter_status.addItem('Todos', '')
        for value, label in _STATUS_LABELS.items():
            self.filter_status.addItem(label, value)
        self.filter_status.currentIndexChanged.connect(self._load_tickets)
        filter_row.addWidget(self.filter_status)

        filter_row.addStretch()

        self.btn_refresh = QPushButton('Atualizar')
        self.btn_refresh.clicked.connect(self._load_tickets)
        filter_row.addWidget(self.btn_refresh)

        layout.addLayout(filter_row)

        # Tabela de tickets
        self.tickets_table = QTableWidget()
        self.tickets_table.setColumnCount(5)
        self.tickets_table.setHorizontalHeaderLabels(
            ['Número', 'Título', 'Tipo', 'Status', 'Data']
        )
        self.tickets_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.tickets_table.setSelectionMode(QTableWidget.SingleSelection)
        self.tickets_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tickets_table.verticalHeader().setVisible(False)
        self.tickets_table.setAlternatingRowColors(True)

        header = self.tickets_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)

        self.tickets_table.cellDoubleClicked.connect(self._on_ticket_double_clicked)
        layout.addWidget(self.tickets_table)

        # Paginação
        page_row = QHBoxLayout()
        page_row.addStretch()

        self.btn_prev_page = QPushButton('< Anterior')
        self.btn_prev_page.clicked.connect(self._prev_page)
        self.btn_prev_page.setEnabled(False)
        page_row.addWidget(self.btn_prev_page)

        self.page_label = QLabel('Página 1')
        page_row.addWidget(self.page_label)

        self.btn_next_page = QPushButton('Próxima >')
        self.btn_next_page.clicked.connect(self._next_page)
        self.btn_next_page.setEnabled(False)
        page_row.addWidget(self.btn_next_page)

        page_row.addStretch()
        layout.addLayout(page_row)

        # Painel de detalhes (inicialmente oculto)
        self.detail_group = QGroupBox('Detalhes do Ticket')
        self.detail_group.hide()
        detail_layout = QVBoxLayout(self.detail_group)

        self.detail_browser = QTextBrowser()
        self.detail_browser.setOpenExternalLinks(False)
        self.detail_browser.setMinimumHeight(200)
        detail_layout.addWidget(self.detail_browser)

        detail_btn_row = QHBoxLayout()
        detail_btn_row.addStretch()
        self.btn_close_detail = QPushButton('Fechar detalhes')
        self.btn_close_detail.clicked.connect(self._close_detail)
        detail_btn_row.addWidget(self.btn_close_detail)
        detail_layout.addLayout(detail_btn_row)

        layout.addWidget(self.detail_group)

    # =========================================================================
    # Aba: Novo Ticket — Ações
    # =========================================================================

    def _on_type_changed(self):
        is_complaint = self.type_combo.currentData() == 'RECLAMACAO'
        self.severity_label.setVisible(is_complaint)
        self.severity_combo.setVisible(is_complaint)

    def _select_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            'Selecionar imagem',
            '',
            'Imagens (*.png *.jpg *.jpeg)'
        )
        if file_path:
            self._set_attachment(file_path)

    def _capture_canvas(self):
        """Captura a janela principal do QGIS (canvas + plugin dock widget)."""
        temp_path = os.path.join(
            tempfile.gettempdir(),
            'fgi_ticket_screenshot.png'
        )
        pixmap = self.iface.mainWindow().grab()
        pixmap.save(temp_path, 'PNG')

        if os.path.isfile(temp_path):
            self._temp_file = temp_path
            self._set_attachment(temp_path)

    def _set_attachment(self, file_path):
        self._attachment_path = file_path
        pixmap = QPixmap(file_path)
        if not pixmap.isNull():
            scaled = pixmap.scaled(
                160, 120,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            self.preview_label.setPixmap(scaled)

        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        size_str = f'{file_size / 1024:.0f} KB'
        if file_size > 1024 * 1024:
            size_str = f'{file_size / (1024 * 1024):.1f} MB'
        self.file_name_label.setText(f'{file_name}\n({size_str})')
        self.btn_remove_attachment.show()

    def _remove_attachment(self):
        self._attachment_path = None
        self.preview_label.clear()
        self.file_name_label.setText('')
        self.btn_remove_attachment.hide()

    def _validate(self):
        if not self.title_edit.text().strip():
            return 'O título é obrigatório.'
        if not self.description_edit.toPlainText().strip():
            return 'A descrição é obrigatória.'
        if self.type_combo.currentData() == 'RECLAMACAO':
            if not self.severity_combo.currentData():
                return 'A severidade é obrigatória para reclamações.'
        if self._attachment_path:
            if not os.path.isfile(self._attachment_path):
                return 'O arquivo anexado não foi encontrado.'
            if os.path.getsize(self._attachment_path) > TicketApiClient.MAX_FILE_SIZE:
                return 'O arquivo excede o limite de 10 MB.'
        return None

    def _ensure_authenticated(self):
        if self.api.is_authenticated():
            return True
        user_name = self._get_user_name()
        self.api.login(_CAMPAIGN, user_name, _PASSWORD)
        return True

    def _submit(self):
        error = self._validate()
        if error:
            QMessageBox.warning(self, 'Validação', error)
            return

        ticket_type = self.type_combo.currentData()
        severity = None
        if ticket_type == 'RECLAMACAO':
            severity = self.severity_combo.currentData()

        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.btn_submit.setEnabled(False)
        try:
            self._ensure_authenticated()

            ticket = self.api.create_ticket(
                title=self.title_edit.text(),
                description=self.description_edit.toPlainText(),
                ticket_type=ticket_type,
                category=self.category_combo.currentData(),
                severity=severity
            )

            ticket_id = ticket.get('_id')
            ticket_number = ticket.get('ticketNumber', '')

            if self._attachment_path and ticket_id:
                self.api.upload_attachment(ticket_id, self._attachment_path)

            QApplication.restoreOverrideCursor()
            self.btn_submit.setEnabled(True)

            QMessageBox.information(
                self,
                'Ticket registrado',
                f'Ticket {ticket_number} criado com sucesso!'
            )

            # Limpar formulário e ir para aba de listagem
            self._clear_form()
            self.tab_widget.setCurrentIndex(1)

        except TicketApiError as e:
            QApplication.restoreOverrideCursor()
            self.btn_submit.setEnabled(True)
            QMessageBox.critical(self, 'Erro', str(e))

    def _clear_form(self):
        self.title_edit.clear()
        self.type_combo.setCurrentIndex(0)
        self.category_combo.setCurrentIndex(0)
        self.severity_combo.setCurrentIndex(0)
        self.description_edit.clear()
        self._remove_attachment()

    # =========================================================================
    # Aba: Meus Tickets — Ações
    # =========================================================================

    def _on_tab_changed(self, index):
        if index == 1:
            self._load_tickets()

    def _load_tickets(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self._ensure_authenticated()

            status_filter = self.filter_status.currentData()
            result = self.api.list_tickets(
                mine=True,
                status=status_filter or None,
                page=self._current_page,
                limit=20
            )

            # A API pode retornar lista direta ou objeto com paginação
            if isinstance(result, list):
                self._tickets_data = result
                self._total_pages = 1
            elif isinstance(result, dict):
                self._tickets_data = result.get('tickets', result.get('data', []))
                total = result.get('total', len(self._tickets_data))
                limit = result.get('limit', 20)
                self._total_pages = max(1, (total + limit - 1) // limit)
            else:
                self._tickets_data = []
                self._total_pages = 1

            self._populate_table()
            self._update_pagination()

        except TicketApiError as e:
            QMessageBox.warning(self, 'Erro', str(e))
        finally:
            QApplication.restoreOverrideCursor()

    def _populate_table(self):
        self.tickets_table.setRowCount(0)
        self.tickets_table.setRowCount(len(self._tickets_data))

        for row, ticket in enumerate(self._tickets_data):
            # Número
            number = ticket.get('ticketNumber', '')
            item_number = QTableWidgetItem(number)
            font = QFont()
            font.setBold(True)
            item_number.setFont(font)
            self.tickets_table.setItem(row, 0, item_number)

            # Título
            title = ticket.get('title', '')
            self.tickets_table.setItem(row, 1, QTableWidgetItem(title))

            # Tipo
            ticket_type = ticket.get('type', '')
            type_label = _TYPE_LABELS.get(ticket_type, ticket_type)
            self.tickets_table.setItem(row, 2, QTableWidgetItem(type_label))

            # Status
            status = ticket.get('status', '')
            status_label = _STATUS_LABELS.get(status, status)
            item_status = QTableWidgetItem(status_label)
            color = _STATUS_COLORS.get(status, '#000000')
            item_status.setForeground(QColor(color))
            font_status = QFont()
            font_status.setBold(True)
            item_status.setFont(font_status)
            self.tickets_table.setItem(row, 3, item_status)

            # Data
            created = ticket.get('createdAt', '')
            if created:
                # Formato ISO → dd/MM/yyyy
                date_str = created[:10]
                try:
                    parts = date_str.split('-')
                    date_str = f'{parts[2]}/{parts[1]}/{parts[0]}'
                except (IndexError, ValueError):
                    pass
            else:
                date_str = ''
            self.tickets_table.setItem(row, 4, QTableWidgetItem(date_str))

    def _update_pagination(self):
        self.page_label.setText(f'Página {self._current_page} de {self._total_pages}')
        self.btn_prev_page.setEnabled(self._current_page > 1)
        self.btn_next_page.setEnabled(self._current_page < self._total_pages)

    def _prev_page(self):
        if self._current_page > 1:
            self._current_page -= 1
            self._load_tickets()

    def _next_page(self):
        if self._current_page < self._total_pages:
            self._current_page += 1
            self._load_tickets()

    def _on_ticket_double_clicked(self, row, _column):
        if row < 0 or row >= len(self._tickets_data):
            return
        ticket = self._tickets_data[row]
        ticket_id = ticket.get('_id')
        if not ticket_id:
            return
        self._show_ticket_detail(ticket_id)

    def _show_ticket_detail(self, ticket_id):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            ticket = self.api.get_ticket(ticket_id)
            self._render_detail(ticket)
            self.detail_group.show()
        except TicketApiError as e:
            QMessageBox.warning(self, 'Erro', str(e))
        finally:
            QApplication.restoreOverrideCursor()

    def _render_detail(self, ticket):
        number = ticket.get('ticketNumber', '')
        title = ticket.get('title', '')
        description = ticket.get('description', '')
        ticket_type = _TYPE_LABELS.get(ticket.get('type', ''), ticket.get('type', ''))
        category = _CATEGORY_LABELS.get(ticket.get('category', ''), ticket.get('category', ''))
        status = ticket.get('status', '')
        status_label = _STATUS_LABELS.get(status, status)
        status_color = _STATUS_COLORS.get(status, '#000000')
        severity = ticket.get('severity', '')
        severity_label = _SEVERITY_LABELS.get(severity, severity) if severity else ''
        author = ticket.get('author', {})
        author_name = author.get('name', '') if isinstance(author, dict) else str(author)
        created = ticket.get('createdAt', '')[:10] if ticket.get('createdAt') else ''
        if created:
            try:
                parts = created.split('-')
                created = f'{parts[2]}/{parts[1]}/{parts[0]}'
            except (IndexError, ValueError):
                pass

        # Construir HTML
        html = f'''
        <h3>{number} — {_escape_html(title)}</h3>
        <table style="margin-bottom: 8px;">
            <tr>
                <td><b>Status:</b></td>
                <td><span style="color: {status_color}; font-weight: bold;">{status_label}</span></td>
                <td style="padding-left: 16px;"><b>Tipo:</b></td>
                <td>{ticket_type}</td>
            </tr>
            <tr>
                <td><b>Categoria:</b></td>
                <td>{category}</td>
                <td style="padding-left: 16px;"><b>Severidade:</b></td>
                <td>{severity_label or '—'}</td>
            </tr>
            <tr>
                <td><b>Autor:</b></td>
                <td>{_escape_html(author_name)}</td>
                <td style="padding-left: 16px;"><b>Data:</b></td>
                <td>{created}</td>
            </tr>
        </table>
        <hr>
        <p>{_escape_html(description).replace(chr(10), '<br>')}</p>
        '''

        # Comentários
        comments = ticket.get('comments', [])
        if comments:
            html += '<hr><h4>Comentários</h4>'
            for comment in comments:
                c_author = comment.get('author', {})
                c_name = c_author.get('name', '') if isinstance(c_author, dict) else str(c_author)
                c_text = comment.get('text', '')
                c_date = comment.get('createdAt', '')[:10] if comment.get('createdAt') else ''
                if c_date:
                    try:
                        parts = c_date.split('-')
                        c_date = f'{parts[2]}/{parts[1]}/{parts[0]}'
                    except (IndexError, ValueError):
                        pass
                is_internal = comment.get('isInternal', False)
                internal_tag = ' <i>(interno)</i>' if is_internal else ''
                html += f'''
                <div style="margin-bottom: 8px; padding: 6px;
                            background: #f5f5f5; border-radius: 4px;">
                    <b>{_escape_html(c_name)}</b>{internal_tag}
                    <span style="color: #888; font-size: small;"> — {c_date}</span>
                    <br>{_escape_html(c_text).replace(chr(10), '<br>')}
                </div>
                '''

        # Histórico de status
        status_history = ticket.get('statusHistory', [])
        if status_history:
            html += '<hr><h4>Histórico de Status</h4>'
            for entry in status_history:
                from_status = _STATUS_LABELS.get(entry.get('from', ''), entry.get('from', ''))
                to_status = _STATUS_LABELS.get(entry.get('to', ''), entry.get('to', ''))
                reason = entry.get('reason', '')
                h_date = entry.get('changedAt', '')[:10] if entry.get('changedAt') else ''
                if h_date:
                    try:
                        parts = h_date.split('-')
                        h_date = f'{parts[2]}/{parts[1]}/{parts[0]}'
                    except (IndexError, ValueError):
                        pass
                h_by = entry.get('changedBy', '')
                html += f'''
                <div style="margin-bottom: 4px;">
                    <b>{from_status}</b> → <b>{to_status}</b>
                    <span style="color: #888; font-size: small;">
                        — {_escape_html(h_by)} em {h_date}
                    </span>
                    {f'<br><i>{_escape_html(reason)}</i>' if reason else ''}
                </div>
                '''

        self.detail_browser.setHtml(html)

    def _close_detail(self):
        self.detail_group.hide()

    # =========================================================================
    # Comum
    # =========================================================================

    def closeEvent(self, event):
        if self._temp_file and os.path.isfile(self._temp_file):
            try:
                os.remove(self._temp_file)
            except OSError:
                pass
        super().closeEvent(event)


def _escape_html(text):
    """Escapa caracteres HTML para exibição segura."""
    return (
        text
        .replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
        .replace('"', '&quot;')
    )
