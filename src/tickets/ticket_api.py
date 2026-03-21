# -*- coding: utf-8 -*-
import os
import mimetypes

import requests


class TicketApiError(Exception):
    """Erro específico da API de tickets."""
    pass


class TicketApiClient:
    """Cliente HTTP para a API de tickets do TVI/LAPIG."""

    BASE_URL = 'https://tvi.lapig.iesa.ufg.br'
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
    ALLOWED_MIME_TYPES = ('image/png', 'image/jpeg')

    VALID_TYPES = ('RECLAMACAO', 'SUGESTAO', 'DUVIDA', 'ELOGIO')
    VALID_CATEGORIES = ('INTERFACE', 'DESEMPENHO', 'FUNCIONALIDADE', 'DADOS', 'OUTRO')
    VALID_SEVERITIES = ('BAIXA', 'MEDIA', 'ALTA', 'CRITICA')

    def __init__(self):
        self.session = requests.Session()

    def login(self, campaign, name, senha):
        """Autentica no TVI. Retorna True se bem-sucedido.

        Args:
            campaign: ID da campanha.
            name: Nome do usuário.
            senha: Senha da campanha ou do administrador.

        Returns:
            True se autenticado com sucesso.

        Raises:
            TicketApiError: Se a autenticação falhar.
        """
        try:
            resp = self.session.post(
                f'{self.BASE_URL}/service/login',
                json={'campaign': campaign, 'name': name, 'senha': senha},
                timeout=15
            )
        except requests.ConnectionError:
            raise TicketApiError('Não foi possível conectar ao servidor TVI.')
        except requests.Timeout:
            raise TicketApiError('Tempo limite excedido ao conectar ao servidor TVI.')

        if resp.status_code == 200:
            return True

        raise TicketApiError('Credenciais inválidas ou campanha não encontrada.')

    def is_authenticated(self):
        """Verifica se a sessão atual é válida.

        Returns:
            True se o usuário está autenticado.
        """
        try:
            resp = self.session.get(
                f'{self.BASE_URL}/service/login/user',
                timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                return bool(data)
            return False
        except (requests.ConnectionError, requests.Timeout, ValueError):
            return False

    def create_ticket(self, title, description, ticket_type, category, severity=None):
        """Cria um novo ticket.

        Args:
            title: Título do ticket (máx. 200 caracteres).
            description: Descrição detalhada.
            ticket_type: Tipo (RECLAMACAO, SUGESTAO, DUVIDA, ELOGIO).
            category: Categoria (INTERFACE, DESEMPENHO, FUNCIONALIDADE, DADOS, OUTRO).
            severity: Severidade (BAIXA, MEDIA, ALTA, CRITICA). Obrigatória se tipo=RECLAMACAO.

        Returns:
            Dicionário com dados do ticket criado, incluindo '_id' e 'ticketNumber'.

        Raises:
            TicketApiError: Se a criação falhar.
        """
        payload = {
            'title': title.strip(),
            'description': description.strip(),
            'type': ticket_type,
            'category': category,
            'origin': 'PLUGIN_FGI',
        }
        if severity:
            payload['severity'] = severity

        try:
            resp = self.session.post(
                f'{self.BASE_URL}/service/tickets',
                json=payload,
                timeout=15
            )
        except requests.ConnectionError:
            raise TicketApiError('Não foi possível conectar ao servidor TVI.')
        except requests.Timeout:
            raise TicketApiError('Tempo limite excedido ao criar o ticket.')

        if resp.status_code == 201:
            return resp.json()
        elif resp.status_code == 401:
            raise TicketApiError('Sessão expirada. Faça login novamente.')
        elif resp.status_code == 400:
            try:
                msg = resp.json().get('error', 'Dados inválidos.')
            except ValueError:
                msg = 'Dados inválidos.'
            raise TicketApiError(f'Erro de validação: {msg}')
        else:
            raise TicketApiError(f'Erro no servidor (HTTP {resp.status_code}).')

    def list_tickets(self, mine=True, status=None, page=1, limit=20):
        """Lista tickets com filtros e paginação.

        Args:
            mine: Se True, lista apenas tickets do usuário autenticado.
            status: Filtro de status (ABERTO, EM_ANALISE, etc.) ou None para todos.
            page: Número da página (a partir de 1).
            limit: Quantidade de tickets por página.

        Returns:
            Dicionário com 'tickets' (lista) e metadados de paginação.

        Raises:
            TicketApiError: Se a requisição falhar.
        """
        params = {
            'origin': 'PLUGIN_FGI',
            'page': page,
            'limit': limit,
        }
        if mine:
            params['mine'] = 'true'
        if status:
            params['status'] = status

        try:
            resp = self.session.get(
                f'{self.BASE_URL}/service/tickets',
                params=params,
                timeout=15
            )
        except requests.ConnectionError:
            raise TicketApiError('Não foi possível conectar ao servidor TVI.')
        except requests.Timeout:
            raise TicketApiError('Tempo limite excedido ao listar tickets.')

        if resp.status_code == 200:
            return resp.json()
        elif resp.status_code == 401:
            raise TicketApiError('Sessão expirada. Faça login novamente.')
        else:
            raise TicketApiError(f'Erro no servidor (HTTP {resp.status_code}).')

    def get_ticket(self, ticket_id):
        """Obtém detalhes de um ticket.

        Args:
            ticket_id: ID do ticket (ObjectID).

        Returns:
            Dicionário com dados completos do ticket.

        Raises:
            TicketApiError: Se a requisição falhar.
        """
        try:
            resp = self.session.get(
                f'{self.BASE_URL}/service/tickets/{ticket_id}',
                timeout=15
            )
        except requests.ConnectionError:
            raise TicketApiError('Não foi possível conectar ao servidor TVI.')
        except requests.Timeout:
            raise TicketApiError('Tempo limite excedido ao obter ticket.')

        if resp.status_code == 200:
            return resp.json()
        elif resp.status_code == 401:
            raise TicketApiError('Sessão expirada. Faça login novamente.')
        elif resp.status_code == 404:
            raise TicketApiError('Ticket não encontrado.')
        else:
            raise TicketApiError(f'Erro no servidor (HTTP {resp.status_code}).')

    def upload_attachment(self, ticket_id, file_path):
        """Envia anexo (imagem) para um ticket existente.

        Args:
            ticket_id: ID do ticket (ObjectID).
            file_path: Caminho absoluto do arquivo PNG ou JPG.

        Returns:
            Dicionário com metadados do anexo.

        Raises:
            TicketApiError: Se o upload falhar.
        """
        if not os.path.isfile(file_path):
            raise TicketApiError(f'Arquivo não encontrado: {file_path}')

        file_size = os.path.getsize(file_path)
        if file_size > self.MAX_FILE_SIZE:
            size_mb = file_size / (1024 * 1024)
            raise TicketApiError(
                f'Arquivo excede o limite de 10 MB ({size_mb:.1f} MB).'
            )

        mime_type, _ = mimetypes.guess_type(file_path)
        if mime_type not in self.ALLOWED_MIME_TYPES:
            raise TicketApiError(
                'Tipo de arquivo não permitido. Apenas PNG e JPG são aceitos.'
            )

        try:
            with open(file_path, 'rb') as f:
                files = {
                    'file': (os.path.basename(file_path), f, mime_type)
                }
                resp = self.session.post(
                    f'{self.BASE_URL}/service/tickets/{ticket_id}/attachments',
                    files=files,
                    timeout=60
                )
        except requests.ConnectionError:
            raise TicketApiError('Não foi possível conectar ao servidor TVI.')
        except requests.Timeout:
            raise TicketApiError('Tempo limite excedido ao enviar o anexo.')

        if resp.status_code == 201:
            return resp.json()
        elif resp.status_code == 401:
            raise TicketApiError('Sessão expirada. Faça login novamente.')
        elif resp.status_code == 400:
            try:
                msg = resp.json().get('error', 'Arquivo inválido.')
            except ValueError:
                msg = 'Arquivo inválido.'
            raise TicketApiError(f'Erro no upload: {msg}')
        else:
            raise TicketApiError(f'Erro no servidor (HTTP {resp.status_code}).')
