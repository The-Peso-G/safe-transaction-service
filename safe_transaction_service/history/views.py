import hashlib
import json

from django.conf import settings

import django_filters
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.filters import OrderingFilter
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView
from web3 import Web3

from safe_transaction_service.version import __version__

from .filters import (DefaultPagination, IncomingTransactionFilter,
                      MultisigTransactionFilter)
from .models import InternalTx, MultisigTransaction, SafeContract, SafeStatus, ModuleTransaction
from .serializers import (IncomingTransactionResponseSerializer,
                          OwnerResponseSerializer,
                          SafeBalanceResponseSerializer,
                          SafeBalanceUsdResponseSerializer,
                          SafeCreationInfoResponseSerializer,
                          SafeMultisigTransactionResponseSerializer,
                          SafeMultisigTransactionSerializer, SafeModuleTransactionResponseSerializer)
from .services import BalanceServiceProvider


class AboutView(APIView):
    """
    Returns info about the project.
    """
    renderer_classes = (JSONRenderer,)

    def get(self, request, format=None):
        content = {
            'name': 'Safe Transaction Service',
            'version': __version__,
            'api_version': self.request.version,
            'secure': self.request.is_secure(),
            'settings': {
                'ETHEREUM_NODE_URL': settings.ETHEREUM_NODE_URL,
                'ETHEREUM_TRACING_NODE_URL': settings.ETHEREUM_TRACING_NODE_URL,
                'ETH_INTERNAL_TXS_BLOCK_PROCESS_LIMIT ': settings.ETH_INTERNAL_TXS_BLOCK_PROCESS_LIMIT,
                'ETH_REORG_BLOCKS': settings.ETH_REORG_BLOCKS,
                'ETH_UNISWAP_FACTORY_ADDRESS': settings.ETH_UNISWAP_FACTORY_ADDRESS,
            }
        }
        return Response(content)


class SafeModuleTransactionListView(ListAPIView):
    filter_backends = (django_filters.rest_framework.DjangoFilterBackend, OrderingFilter)
    ordering_fields = ['created']
    pagination_class = DefaultPagination
    serializer_class = SafeModuleTransactionResponseSerializer

    def get_queryset(self):
        return ModuleTransaction.objects.filter(
            safe=self.kwargs['address']
        ).select_related(
            'internal_tx__ethereum_tx'
        ).order_by(
            '-created'
        )

    @swagger_auto_schema(responses={400: 'Invalid data',
                                    404: 'Not found',
                                    422: 'Invalid ethereum address'})
    def get(self, request, address, format=None):
        """
        Returns the module transaction of a Safe
        """
        if not Web3.isChecksumAddress(address):
            return Response(status=status.HTTP_422_UNPROCESSABLE_ENTITY, data='Invalid ethereum address')

        response = super().get(request, address)
        if response.data['count'] == 0:
            response.status_code = status.HTTP_404_NOT_FOUND
        else:
            response.setdefault('ETag', 'W/' + hashlib.md5(json.dumps(response.data['results']).encode()).hexdigest())

        return response


@swagger_auto_schema(responses={200: 'Ok',
                                404: 'Not found'})
class SafeMultisigTransactionDetailView(RetrieveAPIView):
    serializer_class = SafeMultisigTransactionResponseSerializer
    lookup_field = 'safe_tx_hash'
    lookup_url_kwarg = 'tx_hash'

    def get_queryset(self):
        return MultisigTransaction.objects.with_confirmations_required(
        ).prefetch_related(
            'confirmations'
        ).select_related(
            'ethereum_tx'
        )


class SafeMultisigTransactionListView(ListAPIView):
    filter_backends = (django_filters.rest_framework.DjangoFilterBackend, OrderingFilter)
    filterset_class = MultisigTransactionFilter
    ordering_fields = ['nonce', 'created']
    pagination_class = DefaultPagination

    def get_queryset(self):
        return MultisigTransaction.objects.filter(
            safe=self.kwargs['address']
        ).with_confirmations_required(
        ).prefetch_related(
            'confirmations'
        ).select_related(
            'ethereum_tx'
        ).order_by(
            '-nonce',
            '-created'
        )

    def get_serializer_class(self):
        """
        Proxy returning a serializer class according to the request's verb.
        """
        if self.request.method == 'GET':
            return SafeMultisigTransactionResponseSerializer
        elif self.request.method == 'POST':
            return SafeMultisigTransactionSerializer

    @swagger_auto_schema(responses={400: 'Invalid data',
                                    404: 'Not found',
                                    422: 'Invalid ethereum address'})
    def get(self, request, address, format=None):
        """
        Returns the history of a multisig tx (safe)
        """
        if not Web3.isChecksumAddress(address):
            return Response(status=status.HTTP_422_UNPROCESSABLE_ENTITY, data='Invalid ethereum address')

        response = super().get(request, address)
        if response.data['count'] == 0:
            response.status_code = status.HTTP_404_NOT_FOUND
        else:
            response.data['count_unique_nonce'] = MultisigTransaction.objects.filter(safe=address
                                                                                     ).distinct('nonce').count()
            response.setdefault('ETag', 'W/' + hashlib.md5(json.dumps(response.data['results']).encode()).hexdigest())

        return response

    @swagger_auto_schema(responses={202: 'Accepted',
                                    400: 'Invalid data',
                                    422: 'Invalid ethereum address/User is not an owner or tx not approved/executed'})
    def post(self, request, address, format=None):
        """
        Creates a Multisig Transaction with its confirmations and retrieves all the information related.
        """
        if not Web3.isChecksumAddress(address):
            return Response(status=status.HTTP_422_UNPROCESSABLE_ENTITY, data='Invalid ethereum address')

        request.data['safe'] = address
        serializer = self.get_serializer_class()(data=request.data)

        if not serializer.is_valid():
            return Response(status=status.HTTP_422_UNPROCESSABLE_ENTITY, data=serializer.errors)
        else:
            serializer.save()
            return Response(status=status.HTTP_202_ACCEPTED)


class SafeBalanceView(APIView):
    serializer_class = SafeBalanceResponseSerializer

    @swagger_auto_schema(responses={200: SafeBalanceResponseSerializer(many=True),
                                    404: 'Safe not found',
                                    422: 'Safe address checksum not valid'})
    def get(self, request, address, format=None):
        """
        Get status of the safe
        """
        if not Web3.isChecksumAddress(address):
            return Response(status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        else:
            try:
                SafeContract.objects.get(address=address)
            except SafeContract.DoesNotExist:
                return Response(status=status.HTTP_404_NOT_FOUND)

            safe_balances = BalanceServiceProvider().get_balances(address)
            serializer = self.serializer_class(data=safe_balances, many=True)
            serializer.is_valid()
            return Response(status=status.HTTP_200_OK, data=serializer.data)


class SafeBalanceUsdView(APIView):
    serializer_class = SafeBalanceUsdResponseSerializer

    @swagger_auto_schema(responses={200: SafeBalanceUsdResponseSerializer(many=True),
                                    404: 'Safe not found',
                                    422: 'Safe address checksum not valid'})
    def get(self, request, address, format=None):
        """
        Get status of the safe
        """
        if not Web3.isChecksumAddress(address):
            return Response(status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        else:
            try:
                SafeContract.objects.get(address=address)
            except SafeContract.DoesNotExist:
                return Response(status=status.HTTP_404_NOT_FOUND)

            safe_balances = BalanceServiceProvider().get_usd_balances(address)
            serializer = self.serializer_class(data=safe_balances, many=True)
            serializer.is_valid()
            return Response(status=status.HTTP_200_OK, data=serializer.data)


class SafeIncomingTxListView(ListAPIView):
    filter_backends = (django_filters.rest_framework.DjangoFilterBackend,)
    filterset_class = IncomingTransactionFilter
    serializer_class = IncomingTransactionResponseSerializer
    pagination_class = DefaultPagination

    def filter_queryset(self, queryset):
        # Disable filter queryset, it will try to filter the Union and will fail
        return queryset

    def get_queryset(self):
        address = self.kwargs['address']
        tokens_queryset = super().filter_queryset(InternalTx.objects.incoming_tokens(address))
        ether_queryset = super().filter_queryset(InternalTx.objects.incoming_txs(address))
        return InternalTx.objects.union_incoming_txs_with_tokens(tokens_queryset, ether_queryset)

    @swagger_auto_schema(responses={200: IncomingTransactionResponseSerializer(many=True),
                                    404: 'Txs not found',
                                    422: 'Safe address checksum not valid'})
    def get(self, request, address, format=None):
        """
        Returns the history of a multisig tx (safe)
        """
        if not Web3.isChecksumAddress(address):
            return Response(status=status.HTTP_422_UNPROCESSABLE_ENTITY, data='Invalid ethereum address')

        response = super().get(request, address)
        if response.data['count'] == 0:
            response.status_code = status.HTTP_404_NOT_FOUND
        else:
            response.setdefault('ETag', 'W/' + hashlib.md5(json.dumps(response.data['results']).encode()).hexdigest())

        return response


class SafeCreationView(APIView):
    serializer_class = SafeCreationInfoResponseSerializer

    @swagger_auto_schema(responses={200: OwnerResponseSerializer(),
                                    404: 'Safes not found for that owner',
                                    422: 'Owner address checksum not valid'})
    def get(self, request, address, format=None):
        """
        Get status of the safe
        """
        if not Web3.isChecksumAddress(address):
            return Response(status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        try:
            creation_internal_tx = InternalTx.objects.select_related('ethereum_tx__block').get(contract_address=address)
            previous_internal_tx = creation_internal_tx.get_previous_trace()
            creator = (previous_internal_tx or creation_internal_tx)._from
            created = creation_internal_tx.ethereum_tx.block.timestamp
        except InternalTx.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        serializer = self.serializer_class(data={'creator': creator,
                                                 'created': created,
                                                 'transaction_hash': creation_internal_tx.ethereum_tx_id})
        serializer.is_valid()
        return Response(status=status.HTTP_200_OK, data=serializer.data)


class OwnersView(APIView):
    serializer_class = OwnerResponseSerializer

    @swagger_auto_schema(responses={200: OwnerResponseSerializer(),
                                    404: 'Safes not found for that owner',
                                    422: 'Owner address checksum not valid'})
    def get(self, request, address, format=None):
        """
        Get status of the safe
        """
        if not Web3.isChecksumAddress(address):
            return Response(status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        safes_for_owner = SafeStatus.objects.addresses_for_owner(address)
        if not safes_for_owner:
            return Response(status=status.HTTP_404_NOT_FOUND)

        serializer = self.serializer_class(data={'safes': safes_for_owner})
        serializer.is_valid()
        return Response(status=status.HTTP_200_OK, data=serializer.data)
