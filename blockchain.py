import hashlib
import json
from urllib.parse import urlparse
from time import time
from uuid import uuid4
from textwrap import dedent
from flask import Flask,jsonify,request
from gevent import monkey
from gevent.pywsgi import WSGIServer
#from flask import render_template
#from flask_sqlalchemy import SQLAlchemy
import random as R
import threading

class Blockchain(object):

    def __init__(self):
        #链
        self.chain = []
        #当前交易
        self.current_transactions = []
        #根据URL产生的节点set
        #我们用 set 来储存节点，这是一种避免重复添加节点的简便方法。
        self.nodes = set()
        #每个区块链对象都要有一个最初的区块
        self.new_block(previous_hash=1,proof=100)
    def register_node(self,address):
        '''
        根据URL生成节点列表，所有用户共享节点列表
        :param address: URL地址
        :return:None.
        '''
        parsed_url=urlparse(address)
        # for i in parsed_url:
        #     print(i)
        # print(parsed_url)
        self.nodes.add(parsed_url.netloc)
    def valid_chain(self,chain):
        '''
        检查整个区块链是否有异常
        :param chain: 当前区块链
        :return: True or False
        '''
        last_block = chain[0]
        current_index = 1
        while current_index < len(chain):
            block = chain[current_index]
            print(last_block)
            print(block)
            print("\n-------------\n")
            #检查区块的Hash值是否正确
            if block['previous_hash'] !=self.hash(last_block):
                return False
            #检查Proof of Work是否正确（防止货币造假）
            if not self.valid_proof(last_block['proof'],block['proof']):
                return False
            last_block = block
            current_index += 1
        return True
    def resolve_conflicts(self):
        neighbours = self.nodes
        new_chain = None
        #只寻找比我们的链长的链
        max_length = len(self.chain)
        #获取并验证我们网络中的所有的链
        for node in neighbours:
            response = request.get('http://'+str(node)+'/chain')
            if response.status_code == 200:
                length = response.json()['length']
                chain = response.json()['chain']
                if length > max_length and self.valid_chain(chain):
                    max_length = length
                    new_chain = chain
        #如果我们发现了更长的链，用他来替代我们的链
        if new_chain:
            self.chain = new_chain
            return True
        return False


    def new_block(self,proof,previous_hash=None):
        '''
        创造新的Block并且添加进chain里
        :param proof:工作量证明 下一个问题的条件
        :param previous_hash: 前一个区块的hash值
        :return:当前创建的区块block
        一个区块有五个基本属性：index，timestamp（in Unix time），transaction 列表，proof工作量证明以及前一个区块的 Hash 值。
        '''
        block={
            'index':len(self.chain)+1,
            'timestamp':time(),
            'transactions':self.current_transactions,
            'proof':proof,
            'previous_hash':previous_hash or self.hash(self.chain[-1]),
        }
        #重置当前交易list
        self.current_transactions = []
        self.chain.append(block)
        return block
    def new_fake_block(self,previous_hash=None,recipient=""):
        '''
        创建一个有持有者的Block但是没有proof,分发给所有者自己计算proof,
        算完之后将由客户端回复proof调用finish_fake_block增加交易记录并重新计算账本
        :param previous_hash:上一个块的Hash,用于校验Block的位置
        :param recipient:所有者的用户名
        :return:整个block
        '''
        block={
            'index': len(self.chain) + 1,
            'timestamp': time(),
            'transactions': self.current_transactions,
            'proof':self.last_block['proof'],
            'previous_hash': previous_hash or self.hash(self.chain[-1]),
        }
        self.current_transactions=[]
        self.chain.append(block)
        return block
    def finish_fake_block(self,recipient,block,lastproof):
        '''
        检验proof并完善分发给用户计算的fake_block,并创建交易指向用户
        :param recipient: 接受任务的fake_block持有者用户名
        :param block: 回复的计算完成的block
        :param lastproof: 接到的fake_block的proof（这个proof是fake_block的上一个block的）
        :return: 返回是否成功
        '''
        if(self.valid_proof(lastproof,block['proof'])):
            self.chain[block["index"]-1]['proof']=block['proof']
            tran={
                    "amount": 1,
                    "recipient": recipient,
                    "sender": node_identifier
                }
            self.chain[block["index"]-1]["transactions"].append(tran)
            return True
        return False
    def new_transaction(self,sender,recipient,amount):
        '''
        创造一个新的交易并添加到当前交易里
        :param sender:<str> 发送者的地址
        :param recipient: <str> 接收者的地址
        :param amount: <int> 数量
        :return: <int> 包括这个交易的Block的索引--下一个待挖掘区块
        '''
        self.current_transactions.append({
            'sender':sender,
            'recipient':recipient,
            'amount':amount,
        })
        return self.last_block['index']+1
    def proof_of_work(self,last_proof):
        '''
        得到符合问题的proof
        :param last_proof:上一个区块的proof
        :return: 符合valid_proof()算法的proof
        '''
        proof=0
        while self.valid_proof(last_proof,proof) is False:
            proof +=1
        return proof
    #静态方法
    @staticmethod
    def hash(block):
        #Hashes a Block
        block_string = json.dumps(block,sort_keys=True).encode()
        return hashlib.sha256(block_string).hexdigest()
    @staticmethod
    def valid_proof(last_proof,proof):
        '''
        工作算法，该算法检验proof是否合理
        衡量算法复杂度的办法是修改零的个数。4 个零足够用于演示了，你会发现哪怕多一个零都会大大增加计算出结果所需的时间。
        :param last_proof: 上一个区块的工作量证明
        :param proof:  本区块的工作量证明
        :return: 上一个proof和本区块proof拼接的字符串
                  的Hash值是否以0000开头
        '''
        guess = (str(last_proof)+str(proof)).encode()
        guess_hash = hashlib.sha256(guess).hexdigest()
        return guess_hash[:4] == "0000"
    @property
    def last_block(self):
        #返回在chain中的最后的Block
        return self.chain[-1]

'''
创建HTTP服务
我们将使用 Flask 框架，它十分轻量并且很容易将网络请求映射到 Python 函数。

我们将创建5个接口：

    /transactions/new 创建一个交易并添加到区块

    /mine 告诉服务器去挖掘新的区块

    /chain 返回整个区块链

    /nodes/register 接收以 URL 的形式表示的新节点的列表

    /nodes/resolve 用于执行一致性算法，用于解决任何冲突，确保所有节点拥有正确的链

我们的服务器将扮演区块链网络中的一个节点。
'''


#gevent的猴子魔法
monkey.patch_all()

#创建节点
app = Flask(__name__)
#配置数据库
#为这个节点分配UUID
node_identifier = str(uuid4()).replace('-','')

#创建区块链
bc= Blockchain()

def localmine(user):
    last_block = bc.last_block
    last_proof = last_block['proof']
    proof = bc.proof_of_work(last_proof)
    # 我们需要接受奖励在找到这个新的proof之后
    # 把sender设置为'0'表示这个节点挖到了一个新的coin.
    bc.new_transaction(sender=node_identifier, recipient=user, amount=1)
    # 建立新的区块并将它添加到链中
    block = bc.new_block(proof)
    response = {
        'message': '新区块已添加至用户',
        'index': block['index'],
        'transactions': block['transactions'],
        'proof': block['proof'],
        'previous_hash': block['previous_hash'],
    }
    return response
#mine 服务
@app.route('/mine',methods=['GET'])
def mine():
    '''
    这里运行proof的工作算法来获得下一个proof
    :return:挖出来的新的区块
    '''
    last_block = bc.last_block
    last_proof = last_block['proof']
    proof = bc.proof_of_work(last_proof)
    #我们需要接受奖励在找到这个新的proof之后
    #把sender设置为'0'表示这个节点挖到了一个新的coin.
    bc.new_transaction(sender=node_identifier,recipient=node_identifier,amount=1)
    #建立新的区块并将它添加到链中
    block = bc.new_block(proof)
    response = {
        'message':'新区块已添加',
        'index':block['index'],
        'transactions':block['transactions'],
        'proof':block['proof'],
        'previous_hash':block['previous_hash'],
    }
    return jsonify(response),200
#transactions 服务
@app.route('/transactions/new',methods=['POST'])
def new_transcation():
    '''
    用户发起交易时向服务器发送请求：
    {
     "sender": "my address",
     "recipient": "someone else's address",
     "amount": 5
    }
    '''
    values = request.get_json()
    #检查请求的数据结构
    required=['sender','recipient','amount']
    if not all(k in values for k in required):
        return "错误数据请求",400
    #创建新的交易
    index = bc.new_transaction(values['sender'],values['recipient'],values['amount'])
    response = {'message':"交易将被添加到区块:"+str(index)}
    #201表示 请求已经被实现，而且有一个新的资源已经依据请求的需要而建立，且其 URI 已经随Location 头信息返回。
    return jsonify(response),201

#chain 服务
@app.route('/chain',methods=['GET'])
def full_chain():
    response = {
        'chain':bc.chain,
        'length':len(bc.chain)
    }
    return jsonify(response),200
#nodes register 服务
@app.route('/nodes/register',methods=['GET'])
def register():
    bc.register_node(request.remote_addr)
    response = {
        'AllNode':[i for i in bc.nodes],
    }
    return jsonify(response),200
@app.route('/nodes/resolve',methods=['GET'])
def resolve():
    if bc.resolve_conflicts():
        response={
            'message':True,
        }
    else:
        response = {
            'message': False,
        }
    return response,200


'''
FGO的后台
    /dg  按概率mine并且把属于他的数量返回给他
'''
@app.route('/pre_dg',methods=['GET'])
def predg():
    block=json.dumps(bc.new_fake_block(recipient=request.args.get('username')))
    return block,200
@app.route('/f_pre_dg',methods=['GET'])
def finish_predg():
    user=request.args.get('username')
    block=json.loads(request.args.get('block'))
    lastproof=request.args.get('lastproof')
    re=bc.finish_fake_block(user,block,lastproof)
    return str(re),200

def one_hundred_mine(num,username):
	for i in range(0,num):
		localmine(username)
@app.route('/dg',methods=['GET'])
def dg():
    '''
    按概率mine并且把属于该用户的block返回给他
    :return:属于用户的block的数量
    '''
    username=request.args.get('username')
    p=request.args.get('p')

    num=0
    for i in range(0,100):
        if(float(p)>R.random()):
            num+=1            
    threads=threading.Timer(interval=20,function=one_hundred_mine,args=(num,username,))
    threads.setDaemon(False)
    threads.start()                  
    return str(num), 200
'''
begin=time()
    ti=[]
    for i in range(0,100000):
        print("This is %d times:"%i)
        each1 = time()
        localmine()
        each2=time()
        ti.append(each2-each1)
    end=time()
    #10000次挖掘
    #19:37:30-20:35:17        约1小时1万个
    #25000次挖掘
    # 19:37:30-21:30:00       约2.5小时2.5万个
    #29500次挖掘
    #19:37:30-23:55:50       约4.5小时3万个
    #100000次挖掘
    #约9.86小时
    print(end-begin,"s")
    print(max(ti))
'''
if(__name__=='__main__'):
    #http_server = WSGIServer(('127.0.0.1', 5000), app)
    http_server = WSGIServer(('0.0.0.0', 80), app)
    http_server.serve_forever()
    #app.run(host='0.0.0.0',port=80)








