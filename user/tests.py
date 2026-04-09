"""
Testes de autenticação e perfil de usuário — MyNutri AI
Cobre: cadastro, login, refresh de token, perfil GET/PATCH, validações.
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user_data():
    return {
        'nome': 'Gabriel Rezende',
        'email': 'gabriel@teste.com',
        'senha': 'senhaSegura123',
    }


@pytest.fixture
def create_user(db):
    """Cria um usuário no banco e retorna (user, senha_plaintext)."""
    def _create(email='user@teste.com', nome='Teste User', senha='senhaSegura123'):
        user = User.objects.create_user(
            username=email,
            email=email,
            password=senha,
            first_name=nome,
        )
        return user, senha
    return _create


@pytest.fixture
def auth_client(api_client, create_user):
    """APIClient já autenticado com JWT válido."""
    user, _ = create_user()
    refresh = RefreshToken.for_user(user)
    api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')
    return api_client, user


# ---------------------------------------------------------------------------
# POST /api/v1/auth/register
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestRegister:

    def test_registro_sucesso(self, api_client, user_data):
        response = api_client.post('/api/v1/auth/register', user_data, format='json')
        assert response.status_code == 201
        assert 'token' in response.data
        assert 'refresh' in response.data
        assert response.data['user']['email'] == user_data['email']
        assert response.data['user']['nome'] == user_data['nome']

    def test_registro_cria_usuario_no_banco(self, api_client, user_data):
        api_client.post('/api/v1/auth/register', user_data, format='json')
        assert User.objects.filter(email=user_data['email']).exists()

    def test_registro_email_duplicado(self, api_client, user_data, create_user):
        create_user(email=user_data['email'])
        response = api_client.post('/api/v1/auth/register', user_data, format='json')
        assert response.status_code == 400
        assert 'email' in response.data

    def test_registro_senha_curta(self, api_client):
        data = {'nome': 'Teste', 'email': 'teste@email.com', 'senha': '123'}
        response = api_client.post('/api/v1/auth/register', data, format='json')
        assert response.status_code == 400

    def test_registro_email_obrigatorio(self, api_client):
        data = {'nome': 'Teste', 'senha': 'senhaSegura123'}
        response = api_client.post('/api/v1/auth/register', data, format='json')
        assert response.status_code == 400

    def test_registro_nome_obrigatorio(self, api_client):
        data = {'email': 'teste@email.com', 'senha': 'senhaSegura123'}
        response = api_client.post('/api/v1/auth/register', data, format='json')
        assert response.status_code == 400

    def test_registro_email_normalizado_lowercase(self, api_client):
        data = {'nome': 'Teste', 'email': 'UPPER@EMAIL.COM', 'senha': 'senhaSegura123'}
        api_client.post('/api/v1/auth/register', data, format='json')
        assert User.objects.filter(email='upper@email.com').exists()

    def test_registro_retorna_token_valido(self, api_client, user_data):
        response = api_client.post('/api/v1/auth/register', user_data, format='json')
        token = response.data.get('token')
        assert token is not None
        assert len(token) > 20  # JWT tem pelo menos 3 partes separadas por ponto
        assert token.count('.') == 2


# ---------------------------------------------------------------------------
# POST /api/v1/auth/login
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestLogin:

    def test_login_sucesso(self, api_client, create_user):
        user, senha = create_user(email='login@teste.com')
        response = api_client.post(
            '/api/v1/auth/login',
            {'email': 'login@teste.com', 'password': senha},
            format='json',
        )
        assert response.status_code == 200
        assert 'token' in response.data
        assert 'refresh' in response.data

    def test_login_retorna_dados_do_usuario(self, api_client, create_user):
        user, senha = create_user(email='login2@teste.com', nome='Carlos')
        response = api_client.post(
            '/api/v1/auth/login',
            {'email': 'login2@teste.com', 'password': senha},
            format='json',
        )
        assert response.status_code == 200
        assert response.data['user']['email'] == 'login2@teste.com'
        assert response.data['user']['nome'] == 'Carlos'

    def test_login_senha_errada(self, api_client, create_user):
        create_user(email='errado@teste.com')
        response = api_client.post(
            '/api/v1/auth/login',
            {'email': 'errado@teste.com', 'password': 'senhaErrada!!!'},
            format='json',
        )
        assert response.status_code == 401

    def test_login_usuario_inexistente(self, api_client):
        response = api_client.post(
            '/api/v1/auth/login',
            {'email': 'naoexiste@teste.com', 'password': 'qualquer'},
            format='json',
        )
        assert response.status_code == 401

    def test_login_email_obrigatorio(self, api_client):
        response = api_client.post(
            '/api/v1/auth/login',
            {'password': 'senhaSegura123'},
            format='json',
        )
        assert response.status_code == 400

    def test_login_campo_token_renomeado(self, api_client, create_user):
        """Garante que o campo 'access' foi renomeado para 'token' (padrão da API)."""
        user, senha = create_user(email='token@teste.com')
        response = api_client.post(
            '/api/v1/auth/login',
            {'email': 'token@teste.com', 'password': senha},
            format='json',
        )
        assert 'token' in response.data
        assert 'access' not in response.data


# ---------------------------------------------------------------------------
# POST /api/v1/auth/token/refresh
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestTokenRefresh:

    def test_refresh_token_valido(self, api_client, create_user):
        user, _ = create_user(email='refresh@teste.com')
        refresh = RefreshToken.for_user(user)
        response = api_client.post(
            '/api/v1/auth/token/refresh',
            {'refresh': str(refresh)},
            format='json',
        )
        assert response.status_code == 200
        assert 'access' in response.data

    def test_refresh_token_invalido(self, api_client):
        response = api_client.post(
            '/api/v1/auth/token/refresh',
            {'refresh': 'token.invalido.aqui'},
            format='json',
        )
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# GET/PATCH /api/v1/user/profile
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestUserProfile:

    def test_get_perfil_autenticado(self, auth_client):
        client, user = auth_client
        response = client.get('/api/v1/user/profile')
        assert response.status_code == 200
        assert response.data['email'] == user.email

    def test_get_perfil_sem_autenticacao(self, api_client):
        response = api_client.get('/api/v1/user/profile')
        assert response.status_code == 401

    def test_get_perfil_retorna_campos_corretos(self, auth_client):
        client, user = auth_client
        response = client.get('/api/v1/user/profile')
        assert 'id' in response.data
        assert 'nome' in response.data
        assert 'email' in response.data
        assert 'phone' in response.data
        assert 'date_of_birth' in response.data
        assert 'date_joined' in response.data

    def test_patch_perfil_atualiza_campos(self, auth_client):
        client, user = auth_client
        payload = {
            'first_name': 'NovoPrimeiro',
            'last_name': 'NovoUltimo',
            'phone': '(11) 99999-9999',
        }
        response = client.patch('/api/v1/user/profile', payload, format='json')
        assert response.status_code == 200
        user.refresh_from_db()
        assert user.first_name == 'NovoPrimeiro'
        assert user.last_name == 'NovoUltimo'
        assert user.phone == '(11) 99999-9999'

    def test_patch_perfil_sem_autenticacao(self, api_client):
        response = api_client.patch(
            '/api/v1/user/profile', {'first_name': 'Tentativa'}, format='json'
        )
        assert response.status_code == 401

    def test_patch_perfil_parcial_nao_apaga_outros_campos(self, auth_client):
        """PATCH parcial não deve zerar campos não enviados."""
        client, user = auth_client
        user.first_name = 'Existente'
        user.save()

        client.patch('/api/v1/user/profile', {'phone': '(11) 1111-1111'}, format='json')
        user.refresh_from_db()
        assert user.first_name == 'Existente'  # não foi apagado


# ---------------------------------------------------------------------------
# Segurança — acesso entre usuários
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestIsolamentoDeUsuarios:

    def test_usuario_so_ve_proprio_perfil(self, api_client, create_user):
        user_a, senha_a = create_user(email='a@teste.com', nome='Usuário A')
        user_b, _ = create_user(email='b@teste.com', nome='Usuário B')

        refresh_a = RefreshToken.for_user(user_a)
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh_a.access_token}')

        response = api_client.get('/api/v1/user/profile')
        assert response.status_code == 200
        assert response.data['email'] == 'a@teste.com'
        assert 'b@teste.com' not in str(response.data)
