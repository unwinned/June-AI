import { ECPairFactory } from 'ecpair/ecpair.js';
import * as bitcoin from 'bitcoinjs-lib';
import { BIP32Factory } from 'bip32';
import * as bip39 from 'bip39';
import * as ecc from 'tiny-secp256k1';
import { createHash } from 'crypto';
import {Signer} from "./bip322-js/dist/index.js";
bitcoin.initEccLib(ecc);
const mnemonic = "example crash candy gauge soccer artefact dance used goose solid tray trap";

const ECPair = ECPairFactory(ecc);
const bip321 = BIP32Factory(ecc);
const seed2 = bip39.mnemonicToSeedSync(mnemonic);
const hdKey = bip321.fromSeed(seed2, bitcoin.networks.testnet);
const path3 = "m/86'/0'/0'/0/0";
const child2 = hdKey.derivePath(path3);
const { address } = bitcoin.payments.p2tr({
  internalPubkey: child2.publicKey.slice(1, 33),
  network: bitcoin.networks.testnet,
});
const wif3 = child2.toWIF()

function signMessage(message, privateKey) {
    const messagePrefix = Buffer.from("\x18Bitcoin Signed Message:\n" + message.length.toString() + message, "utf8");
    const hash = createHash("sha256").update(createHash("sha256").update(messagePrefix).digest()).digest();
    const keyPair = ECPair.fromPrivateKey(privateKey);
    const signature = keyPair.sign(hash).toDER();

    return signature.toString("hex");
}
const message = "Please sign this message to prove ownership of your wallet. Unique code: 7058716376698985";

const signature = signMessage(message, child2.privateKey);
console.log(address)
console.log(wif3)
console.log(signature)